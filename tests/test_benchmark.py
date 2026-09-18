import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from snake_lab.database.DbMgr import DbMgr
from snake_lab.database.SnakeDb import SnakeDb

spec = importlib.util.spec_from_file_location(
    "run_benchmark", Path(__file__).resolve().parents[1] / "scripts/run-benchmark.py"
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.rowcount = 1
        self.database = SnakeDb(DbMgr(self.connection))
        self.started = datetime(2026, 1, 1)

    def test_measurement_and_scoped_cleanup(self):
        self.cursor.fetchone.side_effect = [
            {"status": "completed", "started_at": self.started,
             "completed_at": self.started + timedelta(seconds=2)}, {"total": 500},
        ]
        with patch("builtins.print") as output:
            benchmark.measure_and_delete(self.database, "owned-run")
        output.assert_called_once_with(
            "Snake Lab Benchmark: 250 steps per second", flush=True
        )
        self.cursor.execute.assert_called_with(
            "DELETE FROM `simulation_runs` WHERE `run_id` = %s", ("owned-run",)
        )
        self.assertIn("FOR UPDATE", self.cursor.execute.call_args_list[0].args[0])
        self.assertEqual(self.cursor.execute.call_args_list[0].args[1], ("owned-run",))
        self.connection.commit.assert_called_once()
        self.connection.rollback.assert_not_called()

    def test_verbose_includes_details(self):
        self.cursor.fetchone.side_effect = [
            {"status": "completed", "started_at": self.started,
             "completed_at": self.started + timedelta(seconds=2)}, {"total": 500},
        ]
        with patch("builtins.print") as output:
            benchmark.measure_and_delete(self.database, "owned-run", verbose=True)
        self.assertIn("Steps/second: 250", output.call_args_list[0].args[0])
        self.assertIn("Deleted benchmark data", output.call_args_list[1].args[0])
        self.assertEqual(output.call_args_list[2].args[0],
                         "Snake Lab Benchmark: 250 steps per second")

    def test_unfinished_missing_and_invalid_timing_never_delete(self):
        for run in [None, {"status": "running"},
                    {"status": "completed", "started_at": self.started, "completed_at": self.started},
                    {"status": "completed", "started_at": None, "completed_at": None}]:
            with self.subTest(run=run):
                self.connection.reset_mock()
                self.cursor.fetchone.return_value = run
                with self.assertRaises(RuntimeError):
                    benchmark.measure_and_delete(self.database, "owned-run")
                self.connection.rollback.assert_called_once()
                self.connection.commit.assert_not_called()
                self.assertEqual(self.cursor.execute.call_count, 1)

    def test_delete_failure_rolls_back(self):
        self.cursor.fetchone.side_effect = [
            {"status": "completed", "started_at": self.started,
             "completed_at": self.started + timedelta(seconds=1)}, {"total": 100},
        ]
        self.cursor.execute.side_effect = [None, None, RuntimeError("delete failed")]
        with patch("builtins.print"), self.assertRaisesRegex(RuntimeError, "delete failed"):
            benchmark.measure_and_delete(self.database, "owned-run")
        self.connection.rollback.assert_called_once()
        self.connection.commit.assert_not_called()

    def test_missing_delete_and_commit_failure_do_not_report_success(self):
        for failure in ("missing_row", "commit"):
            with self.subTest(failure=failure):
                self.connection.reset_mock()
                self.cursor.fetchone.side_effect = [
                    {"status": "completed", "started_at": self.started,
                     "completed_at": self.started + timedelta(microseconds=1234567)},
                    {"total": 0},
                ]
                self.cursor.rowcount = 0 if failure == "missing_row" else 1
                self.connection.commit.side_effect = RuntimeError("commit failed") if failure == "commit" else None
                with patch("builtins.print") as output, self.assertRaises(RuntimeError):
                    benchmark.measure_and_delete(self.database, "owned-run", verbose=True)
                output.assert_not_called()
                self.connection.rollback.assert_called_once()

    def test_script_delegates_to_application_dal(self):
        database = MagicMock(spec=SnakeDb)
        database.measure_and_delete_benchmark.return_value = (500, 2.0)
        with patch("builtins.print") as output:
            benchmark.measure_and_delete(database, "owned-run")
        database.measure_and_delete_benchmark.assert_called_once_with("owned-run")
        output.assert_called_once_with("Snake Lab Benchmark: 250 steps per second", flush=True)



class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_submission_monitoring_and_cleanup(self):
        client = MagicMock()
        client.active = AsyncMock(return_value={"status": "ok", "payload": {"run": None}})
        client.submit = AsyncMock(return_value={"status": "ok", "payload": {"run_id": "new-run"}})
        client.request = AsyncMock(side_effect=[
            {"status": "ok", "payload": {"state": "running", "completed_epochs": 1}},
            {"status": "ok", "payload": {"state": "completed", "completed_epochs": 2}},
        ])
        connection = MagicMock()
        with patch.object(benchmark, "connect_database", return_value=connection), \
             patch.object(benchmark, "AsyncLabClient", return_value=client), \
             patch.object(benchmark, "measure_and_delete") as cleanup, \
             patch.object(benchmark.asyncio, "sleep", new_callable=AsyncMock), \
             patch("builtins.print") as output:
            await benchmark.benchmark({"epochs": 2})
        output.assert_not_called()
        client.submit.assert_awaited_once_with({"epochs": 2})
        cleanup.assert_called_once_with(connection, "new-run", verbose=False)
        client.close.assert_called_once()
        connection.close.assert_called_once()

    async def test_client_initialization_failure_closes_database(self):
        database = MagicMock(spec=SnakeDb)
        with patch.object(benchmark, "connect_database", return_value=database), \
             patch.object(benchmark, "AsyncLabClient", side_effect=RuntimeError("client failed")):
            with self.assertRaisesRegex(RuntimeError, "client failed"):
                await benchmark.benchmark({})
        database.close.assert_called_once_with()

    async def test_busy_server_does_not_submit(self):
        client = MagicMock()
        client.active = AsyncMock(return_value={"status": "ok", "payload": {"run": {"run_id": "other"}}})
        client.submit = AsyncMock()
        with patch.object(benchmark, "connect_database"), \
             patch.object(benchmark, "AsyncLabClient", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "idle"):
                await benchmark.benchmark({})
        client.submit.assert_not_awaited()

    async def test_failed_run_is_retained(self):
        client = MagicMock()
        client.active = AsyncMock(return_value={"status": "ok", "payload": {"run": None}})
        client.submit = AsyncMock(return_value={"status": "ok", "payload": {"run_id": "failed-run"}})
        client.request = AsyncMock(return_value={"status": "ok", "payload": {"state": "failed", "error": "oops"}})
        with patch.object(benchmark, "connect_database"), \
             patch.object(benchmark, "AsyncLabClient", return_value=client), \
             patch.object(benchmark, "measure_and_delete") as cleanup, \
             patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "oops"):
                await benchmark.benchmark({})
        cleanup.assert_not_called()
