import unittest
from unittest.mock import MagicMock, patch

from textual.widgets import Label, TabbedContent
from textual_plot import PlotWidget
from snake_lab.client import ConfigurationReceived, SnakeLabClient
from snake_lab.client.ConfigurationReader import ConfigurationReader, TUNED_FIELDS
from snake_lab.client.LivePlots import LivePlots
from tests.test_client import FakeControlClient


class ConfigurationReaderTests(unittest.TestCase):
    def test_lookup_is_read_only_and_bound_to_run_id(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"training_learning_rate": 0.0021}
        with patch("snake_lab.database.DbMgr.Path.read_text", return_value='{"password":"secret"}'), patch(
            "snake_lab.database.DbMgr.pymysql.connect", return_value=connection
        ):
            result = ConfigurationReader().read("run-id")
        self.assertEqual(result, {"training_learning_rate": 0.0021})
        self.assertEqual(cursor.execute.call_args_list[0].args, ("START TRANSACTION READ ONLY",))
        query, params = cursor.execute.call_args_list[1].args
        self.assertTrue(query.startswith("SELECT "))
        self.assertEqual(params, ("run-id",))
        self.assertIn("`configurations`", query)
        connection.close.assert_called_once()
        connection.commit.assert_called_once_with()

    def test_connection_closes_on_query_failure(self):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("offline")
        with patch("snake_lab.database.DbMgr.Path.read_text", return_value='{"password":"secret"}'), patch(
            "snake_lab.database.DbMgr.pymysql.connect", return_value=connection
        ):
            with self.assertRaises(RuntimeError):
                ConfigurationReader().read("run-id")
        connection.close.assert_called_once()


class LossBinningTests(unittest.TestCase):
    def test_legacy_bin_boundaries_and_partial_final_bin(self):
        plots = LivePlots()
        self.assertEqual(plots._loss_points(), [])
        for number in range(76):
            plots.add_episode({"episode": number * 2, "score": 0, "loss": float(number)}, 0)
        # The legacy divisor is a target, not a strict 75-point limit.
        self.assertEqual(plots._loss_points(), [(n * 2, float(n)) for n in range(76)])
        for number in range(76, 151):
            plots.add_episode({"episode": number * 2, "score": 0, "loss": float(number)}, 0)
        plots.add_episode({"episode": 301, "score": 0, "loss": None}, 0)
        plots.add_episode({"episode": 301, "score": 0, "loss": 999}, 0)
        points = plots._loss_points()
        self.assertEqual(len(plots.losses), 151)
        self.assertEqual(points[:-1], [(n * 2, n + 0.5) for n in range(0, 150, 2)])
        self.assertEqual(points[-1], (300, 150.0))


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
            self.assertEqual(len(plots.losses), 300)
            loss_plot = plots.query_one("#plot-losses", PlotWidget)
            self.assertEqual(loss_plot._datasets[0].x.tolist(), list(range(0, 600, 8)))
            self.assertEqual(loss_plot._datasets[0].y.tolist(), [0.5] * 75)
            self.assertEqual(len(plots.game_scores), 200)
            score_plot = plots.query_one("#plot-scores", PlotWidget)
            self.assertEqual(score_plot._datasets[0].x.tolist(), list(range(400, 600)))
            # Legacy smoothing uses five points once the 200-point window is full.
            self.assertEqual(score_plot._datasets[1].x.tolist(), list(range(404, 600)))
            self.assertEqual(score_plot._datasets[1].y[0], 2.0)
            self.assertEqual(dict(plots.score_counts), {score: 75 for score in range(8)})
            # Duplicate episode delivery must not inflate the histogram.
            plots.add_episode({"episode": 599, "score": 7}, 7)
            self.assertEqual(sum(plots.score_counts.values()), 600)
            plots.query_one(TabbedContent).active = "tab-distribution"
            await pilot.pause()
            histogram = plots.query_one("#plot-distribution", PlotWidget)
            self.assertTrue(histogram.visible)
            self.assertEqual(histogram._datasets[0].x.tolist(), list(range(8)))
            self.assertEqual(histogram._datasets[0].y.tolist(), [75] * 8)
            self.assertIn("Learning rate", str(app.query_one("#configuration-values", Label).content))
            self.assertIn("5990", str(app.query_one("#total-steps", Label).content))
            app._activate_run("second")
            self.assertEqual(len(plots.episodes), 0)
            self.assertEqual(len(plots.game_scores), 0)
            self.assertEqual(plots.losses, [])
            self.assertEqual(loss_plot._datasets, [])
            self.assertEqual(dict(plots.score_counts), {})
            self.assertEqual(histogram._datasets, [])
            for number in range(1, 40):
                plots.add_episode({"episode": number, "score": 20}, 20)
            plots.redraw()
            self.assertEqual(histogram._datasets[0].x.tolist(), [20])
            self.assertEqual(histogram._datasets[0].y.tolist(), [39])
            # Before 80 observations, the legacy average has a one-point window.
            self.assertEqual(score_plot._datasets[1].x.tolist(), list(range(1, 40)))
            self.assertEqual(score_plot._datasets[1].y.tolist(), [20] * 39)
            app.on_configuration_received(ConfigurationReceived("first", {"training_learning_rate": 999}))
            self.assertNotIn("999", str(app.query_one("#configuration-values", Label).content))
            await pilot.pause()
            app.on_configuration_received(ConfigurationReceived("second", None))
            self.assertIn("unavailable", str(app.query_one("#configuration-values", Label).content))
