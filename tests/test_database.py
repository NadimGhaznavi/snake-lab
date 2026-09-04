import unittest
from unittest.mock import MagicMock

import pymysql

from constants.DSnakeLab import DSnakeLab
from snake_lab.database import (
    MariaDBSimulationStore,
    MemorySimulationStore,
    canonical_config,
    config_hash,
)
from snake_lab.game import Outcome
from snake_lab.simulator import EpisodeResult


class SimulationDatabaseTests(unittest.TestCase):
    def test_canonical_config_and_hash_ignore_key_order(self) -> None:
        first = {"seed": 7, "epochs": 100}
        second = {"epochs": 100, "seed": 7}

        self.assertEqual(canonical_config(first), canonical_config(second))
        self.assertEqual(config_hash(first), config_hash(second))
        self.assertEqual(len(config_hash(first)), 64)

    def test_duplicate_experiment_returns_existing_run(self) -> None:
        store = MemorySimulationStore()
        config = {"epochs": 100, "seed": 7}

        first = store.create_run("run-1", config, DSnakeLab.VERSION)
        second = store.create_run("run-2", config, DSnakeLab.VERSION)
        changed_version = store.create_run("run-3", config, "next-version")

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(second.run_id, "run-1")
        self.assertTrue(changed_version.created)

    def test_episode_and_terminal_state_are_persisted(self) -> None:
        store = MemorySimulationStore()
        store.create_run("run-1", {"epochs": 100}, DSnakeLab.VERSION)
        store.mark_started("run-1")
        result = EpisodeResult(
            episode=1,
            seed=11,
            score=4,
            reward=3.5,
            steps=27,
            outcome=Outcome.WALL,
            epsilon=0.8,
            epsilon_injections=5,
            loss=0.125,
        )

        store.record_episode("run-1", result, 1, 4)
        store.finish_run("run-1", "completed", 1, 4)

        self.assertEqual(store.episodes["run-1"], [result])
        self.assertEqual(store.runs["run-1"]["status"], "completed")
        self.assertEqual(store.runs["run-1"]["episode_count"], 1)
        self.assertEqual(store.runs["run-1"]["high_score"], 4)

    def test_failed_experiment_can_be_restarted_in_place(self) -> None:
        store = MemorySimulationStore()
        config = {"epochs": 100}
        store.create_run("run-1", config, DSnakeLab.VERSION)
        store.finish_run("run-1", "failed", 12, 3, "training failed")

        restarted = store.create_run("run-2", config, DSnakeLab.VERSION)

        self.assertTrue(restarted.created)
        self.assertEqual(restarted.run_id, "run-1")
        self.assertEqual(store.runs["run-1"]["status"], "queued")
        self.assertIsNone(store.runs["run-1"]["episode_count"])
        self.assertIsNone(store.runs["run-1"]["error_message"])

    def test_mariadb_episode_write_and_summary_are_one_transaction(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        store = MariaDBSimulationStore(connection)
        result = EpisodeResult(
            episode=8,
            seed=11,
            score=4,
            reward=3.5,
            steps=27,
            outcome=Outcome.WALL,
            epsilon=0.8,
            epsilon_injections=5,
            loss=0.125,
        )

        store.record_episode("run-1", result, 8, 6)

        self.assertEqual(cursor.execute.call_count, 2)
        self.assertEqual(
            cursor.execute.call_args_list[0].args[1],
            ("run-1", 8, 4, 27, 0.8, 0.125),
        )
        self.assertEqual(
            cursor.execute.call_args_list[1].args[1], (8, 6, "run-1")
        )
        connection.commit.assert_called_once_with()

    def test_mariadb_duplicate_completed_run_is_not_requeued(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = [
            pymysql.err.IntegrityError(1062, "duplicate"),
            None,
        ]
        cursor.fetchone.return_value = {
            "run_id": "existing-run",
            "status": "completed",
        }
        store = MariaDBSimulationStore(connection)

        registration = store.create_run(
            "new-run", {"epochs": 100}, DSnakeLab.VERSION
        )

        self.assertFalse(registration.created)
        self.assertEqual(registration.run_id, "existing-run")
        self.assertEqual(registration.status, "completed")
        connection.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
