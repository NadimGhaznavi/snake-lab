"""Contract checks for the generic database boundary."""

import unittest
from unittest.mock import MagicMock, patch

import pymysql

from snake_lab.database.DbMgr import DatabaseError, DbMgr, SqlValue
from snake_lab.database.SnakeDb import SnakeDb


class DbMgrTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.db = DbMgr(self.connection)

    def test_crud_binds_values_and_returns_results(self):
        hostile = "x'; DROP TABLE records; --"
        self.cursor.lastrowid = 42
        self.assertEqual(self.db.insert("records", {"name": hostile}), 42)
        sql, params = self.cursor.execute.call_args.args
        self.assertNotIn(hostile, sql)
        self.assertEqual(params, (hostile,))
        self.cursor.rowcount = 1
        self.assertEqual(self.db.update("records", {"name": "next"}, where={"id": 42}), 1)
        self.cursor.fetchall.return_value = ({"id": 42},)
        self.assertEqual(self.db.select("records", ("id",), where={"name": hostile}), [{"id": 42}])
        self.assertEqual(self.db.delete("records", where={"id": 42}), 1)
        self.assertEqual(self.connection.commit.call_count, 4)
        self.assertEqual(self.connection.cursor.return_value.__exit__.call_count, 4)

    def test_rejects_unsafe_identifiers_and_unbounded_writes(self):
        with self.assertRaises(ValueError):
            self.db.select("records; DROP TABLE records", ("id",))
        with self.assertRaises(ValueError):
            self.db.insert("records", {"name` = NULL --": "value"})
        with self.assertRaises(ValueError):
            self.db.update("records", {"name": "value"}, where={})
        with self.assertRaises(ValueError):
            self.db.delete("records", where={})
        self.cursor.execute.assert_not_called()

    def test_null_in_and_timestamp_expressions(self):
        self.db.update("records", {"ended": SqlValue.CURRENT_TIMESTAMP},
                       where={"status": ("queued", "running"), "deleted": None})
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("`ended` = CURRENT_TIMESTAMP(6)", sql)
        self.assertIn("`status` IN (%s, %s)", sql)
        self.assertIn("`deleted` IS NULL", sql)
        self.assertEqual(params, ("queued", "running"))

    def test_multi_operation_transaction_commits_once(self):
        with self.db.transaction():
            self.db.insert("records", {"name": "first"})
            self.db.update("records", {"name": "second"}, where={"id": 1})
            self.connection.commit.assert_not_called()
        self.connection.begin.assert_called_once_with()
        self.connection.commit.assert_called_once_with()

    def test_failure_rolls_back_and_preserves_driver_cause(self):
        failure = pymysql.OperationalError(2013, "lost connection")
        self.cursor.execute.side_effect = [1, failure]
        with self.assertRaises(DatabaseError) as raised:
            with self.db.transaction():
                self.db.insert("records", {"name": "first"})
                self.db.update("records", {"name": "second"}, where={"id": 1})
        self.assertIs(raised.exception.__cause__, failure)
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_not_called()
        self.assertFalse(self.db._in_transaction)

    def test_commit_failure_rolls_back(self):
        self.connection.commit.side_effect = pymysql.OperationalError("commit failed")
        with self.assertRaises(DatabaseError):
            self.db.update("records", {"name": "new"}, where={"id": 1})
        self.connection.rollback.assert_called_once_with()

    def test_read_only_transaction_closes_after_lookup(self):
        self.cursor.fetchone.return_value = {"id": 1}
        with self.db.transaction(read_only=True):
            self.assertEqual(self.db.select("records", ("id",), one=True), {"id": 1})
        self.assertEqual(self.cursor.execute.call_args_list[0].args, ("START TRANSACTION READ ONLY",))
        self.connection.commit.assert_called_once_with()

    def test_closed_manager_and_nested_transactions_are_rejected(self):
        with self.db.transaction():
            with self.assertRaises(RuntimeError):
                with self.db.transaction():
                    pass
        self.db.close()
        self.db.close()
        self.connection.close.assert_called_once_with()
        with self.assertRaises(RuntimeError):
            self.db.select("records", ("id",))

    def test_connection_options_and_errors(self):
        with patch("snake_lab.database.DbMgr.Path.read_text", return_value='{"password":"secret", "user":"reader"}'), patch(
            "snake_lab.database.DbMgr.pymysql.connect", return_value=self.connection
        ) as connect:
            db = DbMgr.connect(credentials_file="credentials", host="db", port=3307,
                               user="default", database="example")
            self.assertEqual(connect.call_args.kwargs["user"], "reader")
            self.assertEqual(connect.call_args.kwargs["database"], "example")
            self.assertFalse(connect.call_args.kwargs["autocommit"])
            db.close()
        failure = pymysql.OperationalError("offline")
        with patch("snake_lab.database.DbMgr.Path.read_text", return_value='{"password":"secret"}'), patch(
            "snake_lab.database.DbMgr.pymysql.connect", side_effect=failure
        ), self.assertRaises(DatabaseError) as raised:
            DbMgr.connect(credentials_file="credentials", host="db", port=3306,
                          user="user", database="example")
        self.assertIs(raised.exception.__cause__, failure)


class SnakeDbBoundaryTests(unittest.TestCase):
    def test_mark_started_translates_to_generic_update(self):
        manager = MagicMock(spec=DbMgr)
        SnakeDb(manager).mark_started("run-1")
        manager.update.assert_called_once_with("simulation_runs", {
            "status": "running", "started_at": SqlValue.CURRENT_TIMESTAMP,
        }, where={"run_id": "run-1"})

    def test_connection_does_not_recover_runs(self):
        with patch("snake_lab.database.SnakeDb.DbMgr.connect") as connect:
            database = SnakeDb.connect()
            connect.return_value.update.assert_not_called()
            database.recover_interrupted_runs()
            connect.return_value.update.assert_called_once()
