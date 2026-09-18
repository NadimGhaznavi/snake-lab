"""Live DAL checks against an isolated MariaDB instance.

Set SNAKELAB_TEST_DB_SOCKET to enable. An optional SNAKELAB_TEST_DB_PORT
also enables the real credential-based connection and client lookup test.
Each test creates and drops its own database. Use only a disposable server.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
import uuid

import pymysql

from constants.DSQL import DSQL
from snake_lab.client.ConfigurationReader import ConfigurationReader
from snake_lab.database.DBHelper import config_hash, configuration_values
from snake_lab.database.DbMgr import DatabaseError, DbMgr
from snake_lab.database.SnakeDb import SnakeDb
from snake_lab.server.Configuration import simulation_config_template


@unittest.skipUnless(os.environ.get("SNAKELAB_TEST_DB_SOCKET"), "requires isolated MariaDB")
class DatabaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.socket = os.environ["SNAKELAB_TEST_DB_SOCKET"]
        self.admin = pymysql.connect(unix_socket=self.socket, user="root", autocommit=True,
                                     cursorclass=pymysql.cursors.DictCursor)
        self.addCleanup(self.admin.close)
        self.database = "dal_test_" + uuid.uuid4().hex
        self.execute(f"CREATE DATABASE `{self.database}`")
        self.addCleanup(self.execute, f"DROP DATABASE IF EXISTS `{self.database}`")
        self.admin.select_db(self.database)
        schemas = Path(__file__).resolve().parents[1] / "snake_lab/schemas"
        for version in range(1, 5):
            sql = (schemas / f"database-v{version}.sql").read_text()
            sql = "\n".join(line for line in sql.splitlines() if not line.startswith("--"))
            for statement in sql.split(";"):
                if statement.strip():
                    self.execute(statement)
        self.manager = self.new_manager()
        self.store = SnakeDb(self.manager)
        self.config = simulation_config_template().resolve({})

    def new_manager(self):
        connection = pymysql.connect(unix_socket=self.socket, user="root", database=self.database,
                                     autocommit=False, cursorclass=pymysql.cursors.DictCursor,
                                     init_command="SET time_zone = '+00:00'", read_timeout=5)
        manager = DbMgr(connection)
        self.addCleanup(manager.close)
        return manager

    def execute(self, sql, parameters=()):
        with self.admin.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def row(self, run_id):
        rows = self.execute("SELECT * FROM simulation_runs WHERE run_id = %s", (run_id,))
        return rows[0] if rows else None

    def create(self, run_id="run"):
        self.store.create_run(run_id, self.config, "integration")

    def episode(self, number=1, steps=100):
        return SimpleNamespace(episode=number, score=4, steps=steps, epsilon=0.9, loss=0.125)

    def test_submission_after_idle_connection_timeout(self):
        connection = self.manager._connection
        old_id = connection.thread_id()
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION wait_timeout = 1")
        deadline = time.monotonic() + 5
        while self.execute("SELECT ID FROM information_schema.PROCESSLIST WHERE ID=%s", (old_id,)):
            if time.monotonic() >= deadline:
                self.fail("Test connection did not expire")
            time.sleep(0.05)

        self.create("after-idle")

        self.assertNotEqual(connection.thread_id(), old_id)
        self.assertEqual(self.row("after-idle")["status"], "queued")
        self.assertEqual(self.store.get_configuration("after-idle")["epochs"], self.config["epochs"])
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@session.time_zone AS zone, @@autocommit AS autocommit")
            self.assertEqual(cursor.fetchone(), {"zone": "+00:00", "autocommit": 0})
        connection.commit()

    def test_read_only_lookup_after_connection_is_closed_by_server(self):
        self.create()
        old_id = self.manager._connection.thread_id()
        self.execute("KILL CONNECTION %s", (old_id,))
        self.assertEqual(self.store.get_configuration("run")["epochs"], self.config["epochs"])
        self.assertNotEqual(self.manager._connection.thread_id(), old_id)

    def test_connection_loss_during_transaction_propagates_without_replaying(self):
        with self.assertRaises(DatabaseError) as raised:
            with self.manager.transaction():
                self.manager.insert("simulation_runs", {
                    "run_id": "partial", "project_version": "test",
                    "config_hash": config_hash(self.config), "status": "queued",
                })
                self.execute("KILL CONNECTION %s", (self.manager._connection.thread_id(),))
                self.manager.update("simulation_runs", {"status": "running"}, where={"run_id": "partial"})
        self.assertIsInstance(raised.exception.__cause__, pymysql.Error)
        self.assertIsNone(self.row("partial"))
        self.create("next-run")
        self.assertEqual(self.row("next-run")["status"], "queued")

    def test_full_lifecycle_and_fresh_reads_across_connections(self):
        self.create()
        reader = SnakeDb(self.new_manager())
        row = self.row("run")
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["config_hash"], config_hash(self.config))
        self.assertEqual(reader.get_configuration("run"), dict(zip(
            (p.replace(".", "_") for p in DSQL.CONFIGURATION_PATHS), configuration_values(self.config))))
        self.assertEqual(reader.get_high_score_snapshot("run")["high_score_snapshot"], None)
        self.assertIsNone(reader.get_configuration("absent"))
        self.assertIsNone(reader.get_high_score_snapshot("absent"))
        self.store.mark_started("run")
        self.assertIsInstance(self.row("run")["started_at"], datetime)
        self.store.set_status("run", "paused")
        self.assertEqual(self.row("run")["status"], "paused")
        self.store.set_status("run", "running")
        self.store.record_episode("run", self.episode(), 1, 4)
        self.assertEqual(self.row("run")["episode_count"], 1)
        self.assertEqual(self.row("run")["high_score"], 4)
        self.assertEqual(self.execute("SELECT loss FROM simulation_episodes")[0]["loss"], 0.125)
        snapshot = {"episode": 1, "board": {"score": 4}}
        self.store.finish_run("run", "completed", 1, 4, high_score_snapshot=snapshot)
        self.assertEqual(reader.get_high_score_snapshot("run")["high_score_snapshot"], snapshot)
        self.assertEqual(self.row("run")["status"], "completed")
        self.assertIsInstance(self.row("run")["completed_at"], datetime)

    def test_recovery_changes_only_interrupted_runs(self):
        for state in ("queued", "running", "paused", "cancelling", "completed", "failed", "cancelled"):
            self.create(state)
            self.store.set_status(state, state)
        self.store.recover_interrupted_runs()
        for state in ("queued", "running", "paused", "cancelling"):
            row = self.row(state)
            self.assertEqual(row["status"], "failed")
            self.assertIsNotNone(row["completed_at"])
            self.assertEqual(row["error_message"], "Server stopped before run completed")
        for state in ("completed", "failed", "cancelled"):
            self.assertEqual(self.row(state)["status"], state)
            self.assertIsNone(self.row(state)["error_message"])

    def test_configuration_insert_failure_rolls_back_parent(self):
        self.execute("CREATE TRIGGER reject_config BEFORE INSERT ON configurations FOR EACH ROW "
                     "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'reject config'")
        with self.assertRaises(DatabaseError) as raised:
            self.create()
        self.assertIsInstance(raised.exception.__cause__, pymysql.Error)
        self.assertIsNone(self.row("run"))
        self.assertEqual(self.execute("SELECT * FROM configurations"), ())
        self.execute("DROP TRIGGER reject_config")
        self.create()
        self.assertIsNotNone(self.row("run"))

    def test_episode_summary_failure_rolls_back_episode(self):
        self.create()
        self.execute("CREATE TRIGGER reject_summary BEFORE UPDATE ON simulation_runs FOR EACH ROW "
                     "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'reject summary'")
        with self.assertRaises(DatabaseError):
            self.store.record_episode("run", self.episode(), 1, 4)
        self.assertEqual(self.execute("SELECT * FROM simulation_episodes"), ())
        self.assertIsNone(self.row("run")["episode_count"])

    def test_driver_error_rolls_back_transaction_and_releases_connection(self):
        self.create()
        with self.assertRaises(DatabaseError) as raised:
            with self.manager.transaction():
                self.manager.update("simulation_runs", {"status": "paused"}, where={"run_id": "run"})
                self.manager.insert("configurations", {"run_id": "run"})
        self.assertIsInstance(raised.exception.__cause__, pymysql.Error)
        self.assertEqual(self.row("run")["status"], "queued")
        self.store.set_status("run", "running")
        self.assertEqual(self.row("run")["status"], "running")

    def test_read_only_transaction_rejects_writes_and_releases_connection(self):
        self.create()
        with self.assertRaises(DatabaseError):
            with self.manager.transaction(read_only=True):
                self.manager.update("simulation_runs", {"status": "failed"}, where={"run_id": "run"})
        self.assertEqual(self.row("run")["status"], "queued")
        self.assertIsNotNone(self.store.get_configuration("run"))
        self.store.set_status("run", "running")
        self.assertEqual(self.row("run")["status"], "running")

    def complete_benchmark(self, run_id="run"):
        self.create(run_id)
        self.store.record_episode(run_id, self.episode(1, 100), 1, 4)
        self.store.record_episode(run_id, self.episode(2, 150), 2, 4)
        self.store.finish_run(run_id, "completed", 2, 4)
        start = datetime(2026, 1, 1)
        self.execute("UPDATE simulation_runs SET started_at=%s, completed_at=%s WHERE run_id=%s",
                     (start, start + timedelta(microseconds=1250000), run_id))

    def test_benchmark_aggregation_and_scoped_cascade(self):
        self.complete_benchmark()
        self.complete_benchmark("other")
        self.assertEqual(self.store.measure_and_delete_benchmark("run"), (250, 1.25))
        self.assertIsNone(self.row("run"))
        self.assertEqual(self.execute("SELECT * FROM configurations WHERE run_id='run'"), ())
        self.assertEqual(self.execute("SELECT * FROM simulation_episodes WHERE run_id='run'"), ())
        self.assertIsNotNone(self.row("other"))
        self.assertEqual(len(self.execute("SELECT * FROM simulation_episodes WHERE run_id='other'")), 2)

    def test_benchmark_failure_preserves_all_data(self):
        self.complete_benchmark()
        self.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON simulation_runs FOR EACH ROW "
                     "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'reject delete'")
        with self.assertRaises(DatabaseError):
            self.store.measure_and_delete_benchmark("run")
        self.assertIsNotNone(self.row("run"))
        self.assertIsNotNone(self.store.get_configuration("run"))
        self.assertEqual(len(self.execute("SELECT * FROM simulation_episodes")), 2)
        self.execute("DROP TRIGGER reject_delete")
        self.assertEqual(self.store.measure_and_delete_benchmark("run"), (250, 1.25))

    def test_invalid_benchmarks_are_not_deleted(self):
        self.create()
        for state, start, end in (("queued", None, None), ("completed", None, None),
                                  ("completed", datetime(2026, 1, 1), datetime(2026, 1, 1))):
            with self.subTest(state=state, start=start):
                self.execute("UPDATE simulation_runs SET status=%s, started_at=%s, completed_at=%s",
                             (state, start, end))
                with self.assertRaises(RuntimeError):
                    self.store.measure_and_delete_benchmark("run")
                self.assertIsNotNone(self.row("run"))
                self.assertIsNotNone(self.store.get_configuration("run"))
        with self.assertRaises(RuntimeError):
            self.store.measure_and_delete_benchmark("missing")

    def test_row_lock_blocks_competing_writer_until_rollback(self):
        self.create()
        # Bound lock waits on the separate test connection.
        connection = pymysql.connect(unix_socket=self.socket, user="root", database=self.database,
                                     autocommit=False, cursorclass=pymysql.cursors.DictCursor,
                                     init_command="SET innodb_lock_wait_timeout = 1")
        competing = DbMgr(connection)
        self.addCleanup(competing.close)
        with self.assertRaisesRegex(RuntimeError, "release lock"):
            with self.manager.transaction():
                self.manager.select("simulation_runs", ("run_id",), where={"run_id": "run"},
                                    one=True, for_update=True)
                with self.assertRaises(DatabaseError) as raised:
                    competing.update("simulation_runs", {"status": "running"}, where={"run_id": "run"})
                self.assertEqual(raised.exception.__cause__.args[0], 1205)
                raise RuntimeError("release lock")
        competing.update("simulation_runs", {"status": "running"}, where={"run_id": "run"})
        self.assertEqual(self.row("run")["status"], "running")

    @unittest.skipUnless(os.environ.get("SNAKELAB_TEST_DB_PORT"), "requires isolated TCP listener")
    def test_real_credentials_client_lookup_and_connection_cleanup(self):
        self.create()
        user = "dal_" + uuid.uuid4().hex[:16]
        password = uuid.uuid4().hex
        self.execute("CREATE USER %s@'127.0.0.1' IDENTIFIED BY %s", (user, password))
        self.addCleanup(self.execute, "DROP USER %s@'127.0.0.1'", (user,))
        self.execute(f"GRANT SELECT ON `{self.database}`.* TO %s@'127.0.0.1'", (user,))
        with tempfile.TemporaryDirectory(prefix="snake-dal-credentials-") as folder:
            path = Path(folder) / "credentials.json"
            path.write_text(json.dumps({"user": user, "password": password, "database": self.database}))
            reader = ConfigurationReader(host="127.0.0.1", port=int(os.environ["SNAKELAB_TEST_DB_PORT"]),
                                         credentials_file=str(path))
            self.assertEqual(reader.read("run")["epochs"], self.config["epochs"])
            self.assertIsNone(reader.read("missing"))
            self.assertEqual(self.row("run")["status"], "queued")
            sessions = self.execute("SELECT ID FROM information_schema.PROCESSLIST WHERE USER=%s", (user,))
            self.assertEqual(sessions, ())
            db = SnakeDb.connect(path, host="127.0.0.1", port=int(os.environ["SNAKELAB_TEST_DB_PORT"]))
            try:
                with self.assertRaises(DatabaseError):
                    db.mark_started("run")
            finally:
                db.close()
            self.assertEqual(self.row("run")["status"], "queued")
