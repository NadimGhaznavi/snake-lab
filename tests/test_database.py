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

    def test_repeated_configuration_creates_independent_runs(self) -> None:
        store = MemorySimulationStore()
        config = {"epochs": 100, "seed": 7}

        store.create_run("run-1", config, DSnakeLab.VERSION)
        store.create_run("run-2", config, DSnakeLab.VERSION)

        self.assertEqual(set(store.runs), {"run-1", "run-2"})
        self.assertEqual(store.runs["run-1"]["status"], "queued")
        self.assertEqual(store.runs["run-2"]["status"], "queued")
        self.assertEqual(
            store.runs["run-1"]["config_hash"],
            store.runs["run-2"]["config_hash"],
        )
        self.assertIsNot(store.episodes["run-1"], store.episodes["run-2"])

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

    def test_resubmission_preserves_previous_results_in_every_state(self) -> None:
        for state in (
            "queued", "running", "paused", "cancelling",
            "completed", "failed", "cancelled",
        ):
            with self.subTest(state=state):
                store = MemorySimulationStore()
                config = {"epochs": 100}
                store.create_run("run-1", config, DSnakeLab.VERSION)
                result = EpisodeResult(
                    episode=1, seed=11, score=3, reward=2.0, steps=20,
                    outcome=Outcome.WALL, epsilon=0.8,
                    epsilon_injections=5, loss=0.125,
                )
                store.record_episode("run-1", result, 1, 3)
                error = "training failed" if state == "failed" else None
                store.finish_run("run-1", state, 1, 3, error)
                previous = dict(store.runs["run-1"])

                store.create_run("run-2", config, DSnakeLab.VERSION)

                self.assertEqual(store.runs["run-1"], previous)
                self.assertEqual(store.episodes["run-1"], [result])
                self.assertEqual(store.runs["run-2"]["status"], "queued")
                self.assertEqual(store.episodes["run-2"], [])

    def test_reusing_a_run_id_cannot_overwrite_results(self) -> None:
        store = MemorySimulationStore()
        store.create_run("run-1", {"epochs": 100}, DSnakeLab.VERSION)
        store.finish_run("run-1", "completed", 100, 7)

        with self.assertRaisesRegex(ValueError, "Run ID already exists"):
            store.create_run("run-1", {"epochs": 200}, DSnakeLab.VERSION)

        self.assertEqual(store.runs["run-1"]["status"], "completed")
        self.assertEqual(store.runs["run-1"]["config"], {"epochs": 100})

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

    def test_mariadb_repeated_configuration_inserts_both_runs(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        store = MariaDBSimulationStore(connection)
        config = {"epochs": 100}

        store.create_run("first", config, DSnakeLab.VERSION)
        store.create_run("second", config, DSnakeLab.VERSION)

        self.assertEqual(cursor.execute.call_count, 2)
        for invocation, run_id in zip(
            cursor.execute.call_args_list, ("first", "second")
        ):
            self.assertIn("INSERT INTO simulation_runs", invocation.args[0])
            self.assertEqual(
                invocation.args[1],
                (run_id, DSnakeLab.VERSION, canonical_config(config), config_hash(config)),
            )
        self.assertEqual(connection.commit.call_count, 2)
        connection.rollback.assert_not_called()

    def test_mariadb_insert_failure_rolls_back_and_propagates(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = pymysql.err.IntegrityError(1062, "duplicate ID")
        store = MariaDBSimulationStore(connection)

        with self.assertRaises(pymysql.err.IntegrityError):
            store.create_run("run-1", {"epochs": 100}, DSnakeLab.VERSION)

        cursor.execute.assert_called_once()
        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
