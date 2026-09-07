"""MariaDB integration checks; set SNAKELAB_TEST_DB_SOCKET to opt in.

Uses root with no password on an isolated test server and creates/drops only
its own randomly named database. Never point this at the production server.
"""

import os
from pathlib import Path
import unittest
import uuid

import pymysql

from snake_lab.configuration import simulation_config_template
from snake_lab.database import (
    CONFIGURATION_PATHS,
    MariaDBSimulationStore,
    configuration_values,
)


@unittest.skipUnless(os.environ.get("SNAKELAB_TEST_DB_SOCKET"), "requires test MariaDB socket")
class ConfigurationMigrationTests(unittest.TestCase):
    def test_runtime_writes_reapplication_and_cascade(self):
        connection = pymysql.connect(
            unix_socket=os.environ["SNAKELAB_TEST_DB_SOCKET"],
            user="root",
            autocommit=True,
        )
        database = "configuration_test_" + uuid.uuid4().hex
        schemas = Path(__file__).resolve().parents[1] / "snake_lab" / "schemas"

        def apply(version):
            sql = (schemas / f"database-v{version}.sql").read_text()
            sql = "\n".join(line for line in sql.splitlines() if not line.startswith("--"))
            for statement in sql.split(";"):
                if statement.strip():
                    cursor.execute(statement)

        try:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE `{database}`")
                connection.select_db(database)
                apply(1)
                apply(2)
                config = simulation_config_template().resolve({
                    "seed": 9223372036854775807,
                    "game": {"rewards": {"food": -3.125}},
                    "training": {"learning_rate": 0.0000123456789},
                })
                apply(3)
                columns = ", ".join(p.replace(".", "_") for p in CONFIGURATION_PATHS)
                cursor.execute(f"SELECT run_id, {columns} FROM configurations")
                self.assertEqual(cursor.fetchall(), ())
                apply(3)
                cursor.execute("SELECT COUNT(*) FROM configurations")
                self.assertEqual(cursor.fetchone()[0], 0)

                connection.autocommit(False)
                store = MariaDBSimulationStore(connection)
                store.create_run("new-1", config, "new")
                store.create_run("new-2", config, "new")
                cursor.execute(f"SELECT {columns} FROM configurations WHERE run_id = 'new-1'")
                self.assertEqual(cursor.fetchone(), configuration_values(config))
                apply(3)
                cursor.execute("SELECT COUNT(*) FROM configurations")
                self.assertEqual(cursor.fetchone()[0], 2)
                cursor.execute("DELETE FROM simulation_runs WHERE run_id = 'new-1'")
                cursor.execute("SELECT COUNT(*) FROM configurations WHERE run_id = 'new-1'")
                self.assertEqual(cursor.fetchone()[0], 0)
                connection.commit()
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            connection.close()


if __name__ == "__main__":
    unittest.main()
