import unittest
from unittest.mock import MagicMock, patch

from textual.widgets import Label
from snake_lab.client import ConfigurationReceived, SnakeLabClient
from snake_lab.client_config import ConfigurationReader, TUNED_FIELDS
from snake_lab.client_plots import LivePlots
from tests.test_client import FakeControlClient


class ConfigurationReaderTests(unittest.TestCase):
    def test_lookup_is_read_only_and_bound_to_run_id(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"training_learning_rate": 0.0021}
        with patch("snake_lab.client_config.Path.read_text", return_value='{"password":"secret"}'), patch(
            "snake_lab.client_config.pymysql.connect", return_value=connection
        ):
            result = ConfigurationReader().read("run-id")
        self.assertEqual(result, {"training_learning_rate": 0.0021})
        self.assertEqual(cursor.execute.call_args_list[0].args, ("START TRANSACTION READ ONLY",))
        query, params = cursor.execute.call_args_list[1].args
        self.assertTrue(query.startswith("SELECT "))
        self.assertEqual(params, ("run-id",))
        self.assertNotIn("seed", query)
        self.assertNotIn("epochs", query)
        self.assertNotIn("model_layers", query)
        connection.close.assert_called_once()
        connection.commit.assert_not_called()

    def test_connection_closes_on_query_failure(self):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("offline")
        with patch("snake_lab.client_config.Path.read_text", return_value='{"password":"secret"}'), patch(
            "snake_lab.client_config.pymysql.connect", return_value=connection
        ):
            with self.assertRaises(RuntimeError):
                ConfigurationReader().read("run-id")
        connection.close.assert_called_once()


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_plots_are_bounded_and_reset_between_runs(self):
        reader = MagicMock()
        reader.read.return_value = {key: 1 for key, _ in TUNED_FIELDS}
        app = SnakeLabClient(telemetry_port=59999, control_client=FakeControlClient(), configuration_reader=reader)
        async with app.run_test(size=(120, 55)) as pilot:
            app._activate_run("first")
            await pilot.pause()
            plots = app.query_one(LivePlots)
            for number in range(600):
                app._show_episode({"episode": {"episode": number, "score": number % 8,
                                               "loss": None if number % 2 else 0.5},
                                   "summary": {"high_score": 7, "total_steps": number * 10}})
            plots.redraw()
            self.assertEqual(len(plots.episodes), 500)
            self.assertEqual(plots.episodes[0][0], 100)
            self.assertIn("Learning rate", str(app.query_one("#configuration-values", Label).content))
            self.assertIn("5990", str(app.query_one("#total-steps", Label).content))
            app._activate_run("second")
            self.assertEqual(len(plots.episodes), 0)
            app.on_configuration_received(ConfigurationReceived("first", {"training_learning_rate": 999}))
            self.assertNotIn("999", str(app.query_one("#configuration-values", Label).content))
            await pilot.pause()
            app.on_configuration_received(ConfigurationReceived("second", None))
            self.assertIn("unavailable", str(app.query_one("#configuration-values", Label).content))
