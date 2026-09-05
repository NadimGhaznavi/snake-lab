import asyncio
import unittest
from unittest.mock import Mock, call

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
        self.ended = Mock()
        self.server.events.offer_simulation_ended = self.ended

    async def asyncTearDown(self) -> None:
        await self.server._shutdown_worker()
        await self.server.events.close()
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
        self.assertEqual(
            self.ended.call_args_list,
            [call("first", "completed", None), call("second", "completed", None)],
        )

    async def test_worker_failure_does_not_stop_later_runs(self) -> None:
        async def execute(run: SimulationRun) -> None:
            if run.run_id == "first":
                raise RuntimeError("test failure")

        self.server._execute_simulation = execute
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
        self.assertEqual(
            self.ended.call_args_list,
            [
                call("first", "failed", "test failure"),
                call("second", "completed", None),
            ],
        )

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
        self.assertEqual(
            self.ended.call_args_list,
            [call("first", "cancelled", None), call("second", "cancelled", None)],
        )

    async def test_runtime_cancel_continues_to_the_next_run(self) -> None:
        started = asyncio.Event()

        async def execute(run: SimulationRun) -> None:
            if run.run_id == "first":
                started.set()
                while True:
                    await run.control.checkpoint()

        self.server._execute_simulation = execute
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
        self.ended.assert_not_called()
        await self.server._run_queue.join()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(first.state, "cancelled")
        self.assertEqual(second.state, "completed")
        self.assertEqual(
            self.ended.call_args_list,
            [call("first", "cancelled", None), call("second", "completed", None)],
        )

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
        self.ended.assert_not_called()

    async def test_queued_cancel_emits_once_even_on_shutdown(self) -> None:
        run = SimulationRun("queued-run", {"epochs": 100})
        self.server._runs[run.run_id] = run
        self.server._run_queue.put_nowait(run)

        for _attempt in range(2):
            response = self.server.handle_request(
                self._request("simulation.cancel", {"run_id": run.run_id})
            )
            self.assertEqual(response["payload"]["state"], "cancelled")
        await self.server._shutdown_worker()

        self.ended.assert_called_once_with(run.run_id, "cancelled", None)

    async def test_cancelled_queue_entry_does_not_emit_again_in_worker(self) -> None:
        run = SimulationRun("queued-run", {"epochs": 100})
        self.server._runs[run.run_id] = run
        self.server._run_queue.put_nowait(run)
        self.server.handle_request(
            self._request("simulation.cancel", {"run_id": run.run_id})
        )
        self.server._worker_task = asyncio.create_task(
            self.server._worker_loop()
        )
        await asyncio.wait_for(self.server._run_queue.join(), 1)

        self.ended.assert_called_once_with(run.run_id, "cancelled", None)

    async def test_repeated_completed_run_gets_its_own_persisted_ended_event(self) -> None:
        self.server.store = MemorySimulationStore()

        def check_persisted(run_id: str, state: str, error: str | None) -> None:
            saved = self.server.store.runs[run_id]
            self.assertEqual(saved["status"], state)
            self.assertEqual(saved["episode_count"], 100)
            self.assertEqual(saved["high_score"], 7)
            self.assertEqual(saved["error_message"], error)

        async def execute(run: SimulationRun) -> None:
            run.completed_epochs = 100
            run.high_score = 7

        self.ended.side_effect = check_persisted
        self.server._execute_simulation = execute
        request = self._request("simulation.submit", {"config": {}})
        response = self.server.handle_request(request)
        self.server._worker_task = asyncio.create_task(
            self.server._worker_loop()
        )
        await asyncio.wait_for(self.server._run_queue.join(), 1)
        repeated = self.server.handle_request(request)

        self.assertEqual(repeated["payload"]["state"], "queued")
        first_id = response["payload"]["run_id"]
        second_id = repeated["payload"]["run_id"]
        self.assertNotEqual(first_id, second_id)
        await asyncio.wait_for(self.server._run_queue.join(), 1)
        self.assertEqual(
            self.ended.call_args_list,
            [call(first_id, "completed", None), call(second_id, "completed", None)],
        )

    async def test_storage_failure_does_not_emit_an_ended_event(self) -> None:
        self.server.store.finish_run = Mock(
            side_effect=RuntimeError("database unavailable")
        )
        run = SimulationRun("run-1", {"epochs": 100}, state="cancelled")

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.server._finish_run(run)

        self.ended.assert_not_called()

    async def test_repeated_submission_queues_a_new_run(self) -> None:
        self.server.store = MemorySimulationStore()
        first = self.server.handle_request(
            self._request("simulation.submit", {"config": {}})
        )
        second = self.server.handle_request(
            self._request("simulation.submit", {"config": {}})
        )

        self.assertEqual(first["status"], "ok")
        self.assertNotEqual(
            second["payload"]["run_id"], first["payload"]["run_id"]
        )
        self.assertEqual(second["payload"]["state"], "queued")
        self.assertEqual(second["payload"]["queue_position"], 2)
        self.assertNotIn("duplicate", second["payload"])
        self.assertEqual(self.server._run_queue.qsize(), 2)
        self.ended.assert_not_called()

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
