import asyncio
import unittest

from snake_lab.database import MemorySimulationStore
from snake_lab.protocol import PROTOCOL_VERSION
from snake_lab.server import SimulationRun, SnakeLabServer


class FakeLog:
    def info(self, _message: str) -> None:
        pass

    def error(self, _message: str) -> None:
        pass


class FakeStore:
    def mark_started(self, _run_id: str) -> None:
        pass

    def set_status(self, _run_id: str, _status: str) -> None:
        pass

    def finish_run(self, *_args, **_kwargs) -> None:
        pass

    def close(self) -> None:
        pass


class AsyncWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = SnakeLabServer(
            address="127.0.0.1",
            port=0,
            log_file=None,
            store=FakeStore(),
        )
        self.server.log = FakeLog()

    async def asyncTearDown(self) -> None:
        await self.server._shutdown_worker()
        await self.server.telemetry.close()
        self.server._socket.close()
        self.server._context.term()

    async def test_worker_executes_runs_serially_in_fifo_order(self) -> None:
        order: list[str] = []
        active = 0
        maximum_active = 0

        async def execute(run: SimulationRun) -> None:
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            order.append(f"start:{run.run_id}")
            await asyncio.sleep(0)
            order.append(f"finish:{run.run_id}")
            active -= 1

        self.server._execute_simulation = execute
        self.server._write_results = lambda _run: None
        first = SimulationRun("first", {"epochs": 100})
        second = SimulationRun("second", {"epochs": 100})
        self.server._run_queue.put_nowait(first)
        self.server._run_queue.put_nowait(second)
        self.server._worker_task = asyncio.create_task(
            self.server._worker_loop()
        )

        await self.server._run_queue.join()

        self.assertEqual(maximum_active, 1)
        self.assertEqual(
            order,
            [
                "start:first",
                "finish:first",
                "start:second",
                "finish:second",
            ],
        )
        self.assertEqual(first.state, "completed")
        self.assertEqual(second.state, "completed")

    async def test_worker_failure_does_not_stop_later_runs(self) -> None:
        async def execute(run: SimulationRun) -> None:
            if run.run_id == "first":
                raise RuntimeError("test failure")

        self.server._execute_simulation = execute
        self.server._write_results = lambda _run: None
        first = SimulationRun("first", {"epochs": 100})
        second = SimulationRun("second", {"epochs": 100})
        self.server._run_queue.put_nowait(first)
        self.server._run_queue.put_nowait(second)
        self.server._worker_task = asyncio.create_task(
            self.server._worker_loop()
        )

        await self.server._run_queue.join()

        self.assertEqual(first.state, "failed")
        self.assertEqual(second.state, "completed")

    async def test_fatal_worker_failure_is_reported_to_server(self) -> None:
        async def fail() -> None:
            raise RuntimeError("database unavailable")

        self.server._worker_task = asyncio.create_task(fail())
        await asyncio.sleep(0)

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.server._check_worker()

    async def test_shutdown_cancels_active_and_queued_runs(self) -> None:
        started = asyncio.Event()

        async def execute(_run: SimulationRun) -> None:
            started.set()
            await asyncio.Event().wait()

        self.server._execute_simulation = execute
        first = SimulationRun("first", {"epochs": 100})
        second = SimulationRun("second", {"epochs": 100})
        self.server._run_queue.put_nowait(first)
        self.server._run_queue.put_nowait(second)
        self.server._worker_task = asyncio.create_task(
            self.server._worker_loop()
        )
        await started.wait()

        await self.server._shutdown_worker()

        self.assertEqual(first.state, "cancelled")
        self.assertEqual(second.state, "cancelled")
        self.assertEqual(self.server._run_queue.qsize(), 0)

    async def test_runtime_cancel_continues_to_the_next_run(self) -> None:
        started = asyncio.Event()

        async def execute(run: SimulationRun) -> None:
            if run.run_id == "first":
                started.set()
                while True:
                    await run.control.checkpoint()

        self.server._execute_simulation = execute
        self.server._write_results = lambda _run: None
        first = SimulationRun("first", {"epochs": 100})
        second = SimulationRun("second", {"epochs": 100})
        self.server._runs = {"first": first, "second": second}
        self.server._run_queue.put_nowait(first)
        self.server._run_queue.put_nowait(second)
        self.server._worker_task = asyncio.create_task(
            self.server._worker_loop()
        )
        await started.wait()

        response = self.server.handle_request(
            self._request("simulation.cancel", {"run_id": "first"})
        )
        await self.server._run_queue.join()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(first.state, "cancelled")
        self.assertEqual(second.state, "completed")

    async def test_runtime_state_and_delay_requests(self) -> None:
        run = SimulationRun("active-run", {"epochs": 100}, state="running")
        self.server._runs[run.run_id] = run

        paused = self.server.handle_request(
            self._request("simulation.pause", {"run_id": run.run_id})
        )
        delayed = self.server.handle_request(
            self._request(
                "simulation.set_move_delay",
                {"run_id": run.run_id, "move_delay_ms": 80},
            )
        )
        active = self.server.handle_request(
            self._request("simulation.active", {})
        )
        resumed = self.server.handle_request(
            self._request("simulation.resume", {"run_id": run.run_id})
        )

        self.assertEqual(paused["payload"]["state"], "paused")
        self.assertEqual(delayed["payload"]["move_delay_ms"], 80)
        self.assertEqual(active["payload"]["run"]["run_id"], run.run_id)
        self.assertEqual(resumed["payload"]["state"], "running")
        self.assertFalse(run.control.paused)

    async def test_duplicate_submission_returns_existing_run(self) -> None:
        self.server.store = MemorySimulationStore()
        first = self.server.handle_request(
            self._request("simulation.submit", {"config": {}})
        )
        second = self.server.handle_request(
            self._request("simulation.submit", {"config": {}})
        )

        self.assertEqual(first["status"], "ok")
        self.assertEqual(
            second["payload"]["run_id"], first["payload"]["run_id"]
        )
        self.assertTrue(second["payload"]["duplicate"])
        self.assertEqual(self.server._run_queue.qsize(), 1)

    @staticmethod
    def _request(method: str, payload: dict) -> dict:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "request-1",
            "method": method,
            "payload": payload,
        }


if __name__ == "__main__":
    unittest.main()
