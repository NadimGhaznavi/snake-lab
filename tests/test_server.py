import asyncio
import unittest

from snake_lab.server import SimulationRun, SnakeLabServer


class FakeLog:
    def info(self, _message: str) -> None:
        pass

    def error(self, _message: str) -> None:
        pass


class AsyncWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = SnakeLabServer(
            address="127.0.0.1",
            port=0,
            log_file=None,
        )
        self.server.log = FakeLog()

    async def asyncTearDown(self) -> None:
        await self.server._shutdown_worker()
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


if __name__ == "__main__":
    unittest.main()
