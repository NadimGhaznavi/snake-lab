import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from textual.widgets import Button, Checkbox, Input, Label, Select

from snake_lab.board import SnakeBoard
from snake_lab.game import Outcome
from snake_lab.telemetry import (
    TOPIC_EPISODE,
    TOPIC_FRAME,
    TOPIC_RUN,
    BoardSnapshot,
    FrameTelemetry,
    TelemetryEnvelope,
)
from snake_lab.client import SnakeLabClient, TelemetryReceived


class FakeControlClient:
    def __init__(self) -> None:
        self.operations = []
        self.closed = False

    @staticmethod
    def _response(run_id: str, state: str, delay: int) -> dict:
        return {
            "protocol_version": 1,
            "request_id": "test",
            "status": "ok",
            "payload": {
                "run_id": run_id,
                "state": state,
                "epochs": 100,
                "completed_epochs": 12,
                "total_steps": 70,
                "high_score": 5,
                "total_reward": 1.0,
                "epsilon_injections": 10,
                "last_loss": 0.125,
                "move_delay_ms": delay,
                "last_episode": None,
            },
        }

    async def active(self) -> dict:
        return {
            "protocol_version": 1,
            "request_id": "test",
            "status": "ok",
            "payload": {"run": None},
        }

    async def submit(self, config: dict) -> dict:
        self.operations.append(("submit", config))
        return {
            "protocol_version": 1,
            "request_id": "test",
            "status": "ok",
            "payload": {
                "run_id": "submitted-run-1",
                "state": "queued",
                "queue_position": 1,
            },
        }

    async def pause(self, run_id: str) -> dict:
        self.operations.append(("pause", run_id))
        return self._response(run_id, "paused", 0)

    async def resume(self, run_id: str) -> dict:
        self.operations.append(("resume", run_id))
        return self._response(run_id, "running", 0)

    async def cancel(self, run_id: str) -> dict:
        self.operations.append(("cancel", run_id))
        return self._response(run_id, "cancelling", 100)

    async def set_move_delay(self, run_id: str, delay: int) -> dict:
        self.operations.append(("delay", run_id, delay))
        return self._response(run_id, "running", delay)

    def close(self) -> None:
        self.closed = True


class SnakeLabClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_game_is_fixed_while_other_panels_stretch(self) -> None:
        app = SnakeLabClient(
            telemetry_port=59999, control_client=FakeControlClient()
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            board_panel = app.query_one("#board-panel")
            title = app.query_one("#title")
            controls_panel = app.query_one("#controls-panel")
            status_panel = app.query_one("#status-panel")
            event_log = app.query_one("#event-log")
            initial_controls = controls_panel.region
            initial_events = event_log.region

            self.assertEqual(board_panel.region.size, (44, 22))
            self.assertEqual(
                app.query_one("#board", SnakeBoard).region.size, (40, 20)
            )
            self.assertEqual(event_log.region.y, board_panel.region.bottom)
            self.assertEqual(title.region.width, app.size.width)
            self.assertEqual(event_log.region.width, app.size.width)
            self.assertEqual(
                status_panel.region.y, controls_panel.region.bottom
            )

            await pilot.resize_terminal(140, 50)

            self.assertEqual(board_panel.region.size, (44, 22))
            self.assertGreater(
                controls_panel.region.width, initial_controls.width
            )
            self.assertEqual(
                controls_panel.region.height, initial_controls.height
            )
            self.assertEqual(title.region.width, app.size.width)
            self.assertEqual(event_log.region.width, app.size.width)
            self.assertGreater(event_log.region.height, initial_events.height)

    async def test_controls_are_visible_in_a_compact_terminal(self) -> None:
        app = SnakeLabClient(
            telemetry_port=59999, control_client=FakeControlClient()
        )
        async with app.run_test(size=(100, 20)) as pilot:
            await pilot.pause()

            for selector in (
                "#submit-config",
                "#pause-resume",
                "#cancel-run",
                "#move-delay",
                "#display-every",
                "#show-only-highscores",
            ):
                widget = app.query_one(selector)
                self.assertGreater(widget.region.height, 0)
                self.assertLessEqual(widget.region.bottom, app.size.height)

            delay_select = app.query_one("#move-delay", Select)
            self.assertEqual(
                [value for _label, value in delay_select._options],
                [0, 20, 40, 60, 80, 100],
            )

    async def test_frame_interval_holds_snapshots_and_can_change_live(self) -> None:
        control = FakeControlClient()
        app = SnakeLabClient(telemetry_port=59999, control_client=control)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            interval = app.query_one("#display-every", Input)
            board = app.query_one("#board", SnakeBoard)
            interval.value = "3"
            await pilot.pause()

            def receive(sequence: int, run_id: str = "snapshot-run") -> None:
                frame = FrameTelemetry(
                    episode=sequence + 1, step=sequence, action=1,
                    reward=0.0, done=True, outcome=Outcome.EMPTY,
                    board=BoardSnapshot(
                        width=20, height=20, snake_head=(sequence, 1),
                        snake_body=(), food=(19, 19), direction=(1, 0),
                        score=sequence,
                    ),
                )
                app.on_telemetry_received(TelemetryReceived(
                    TOPIC_FRAME,
                    TelemetryEnvelope(sequence, run_id, frame.to_dict()),
                ))

            receive(0)
            first = board.snapshot
            receive(1)
            receive(2)
            self.assertEqual(board.snapshot, first)
            receive(3)
            self.assertEqual(board.snapshot.score, 3)
            self.assertEqual(app._sequences[TOPIC_FRAME], 3)

            for invalid in ("0", "-2", "", "1.5"):
                interval.value = invalid
                await pilot.pause()
                self.assertEqual(app._display_every, 3)

            receive(4, "next-run")
            self.assertEqual(board.snapshot.score, 4)
            receive(5, "next-run")
            self.assertEqual(board.snapshot.score, 4)
            interval.value = "1"
            await pilot.pause()
            receive(6, "next-run")
            self.assertEqual(board.snapshot.score, 6)
            receive(7, "next-run")
            self.assertEqual(board.snapshot.score, 7)
            self.assertEqual(control.operations, [])

    async def test_run_highscores_hold_across_episodes_and_bypass_sampling(self) -> None:
        control = FakeControlClient()
        app = SnakeLabClient(telemetry_port=59999, control_client=control)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            interval = app.query_one("#display-every", Input)
            checkbox = app.query_one("#show-only-highscores", Checkbox)
            board = app.query_one("#board", SnakeBoard)
            interval.value = "100"
            await pilot.pause()
            app._activate_run("first-run")

            step = 0

            def frame(episode: int, score: int) -> None:
                nonlocal step
                step += 1
                app._show_frame(FrameTelemetry(
                    episode=episode, step=step, action=1,
                    reward=0.0, done=False, outcome=Outcome.EMPTY,
                    board=BoardSnapshot(
                        width=20, height=20, snake_head=(step, 1),
                        snake_body=(), food=(19, 19), direction=(1, 0),
                        score=score,
                    ),
                ))

            def complete(episode: int, score: int, high: int) -> None:
                app._show_episode({
                    "episode": {"episode": episode, "score": score},
                    "summary": {"high_score": high,
                                "completed_epochs": episode, "epochs": 100},
                })

            frame(1, 0)
            checkbox.value = True
            await pilot.pause()
            self.assertIsNone(board.snapshot)
            self.assertTrue(interval.disabled)
            self.assertTrue(app.query_one("#frame-display").disabled)
            self.assertEqual(interval.value, "100")
            frame(2, 0)
            self.assertIsNone(board.snapshot)
            frame(2, 1)
            self.assertEqual(board.snapshot.score, 1)
            record = board.snapshot
            frame(2, 1)
            self.assertEqual(board.snapshot, record)
            frame(2, 3)
            self.assertEqual(board.snapshot.score, 3)
            record = board.snapshot
            complete(2, 3, 3)
            self.assertEqual(board.snapshot, record)
            for score in (0, 1, 3):
                frame(3, score)
                self.assertEqual(board.snapshot, record)
            complete(3, 3, 3)
            self.assertEqual(str(app.query_one("#progress", Label).render()),
                             "Progress: 3/100")
            frame(4, 4)
            self.assertEqual(board.snapshot.score, 4)
            record = board.snapshot
            # Respect records reported for episodes whose frames were missed.
            with patch.object(app, "_write_event", wraps=app._write_event) as log:
                complete(5, 7, 7)
                app._refresh_highscore_board()
                self.assertEqual(
                    sum("Dropped frames" in call.args[0] for call in log.call_args_list),
                    1,
                )
            self.assertEqual(app.query_one("#board-panel").border_subtitle,
                             "Not Available")
            self.assertEqual(str(app.query_one("#score", Label).render()),
                             "Score: 4  High: 7")
            frame(6, 6)
            self.assertEqual(board.snapshot, record)
            # A frame matching an already announced record must be accepted.
            frame(6, 7)
            self.assertEqual(board.snapshot.score, 7)
            self.assertEqual(app.query_one("#board-panel").border_subtitle,
                             "Score 7")
            self.assertEqual(str(app.query_one("#score", Label).render()),
                             "Score: 7  High: 7")
            record = board.snapshot
            frame(6, 7)
            self.assertEqual(board.snapshot, record)
            frame(6, 8)
            self.assertEqual(board.snapshot.score, 8)

            app._activate_run("second-run")
            self.assertIsNone(board.snapshot)
            frame(1, 1)
            complete(1, 1, 1)
            self.assertEqual(board.snapshot.score, 1)
            checkbox.value = False
            await pilot.pause()
            self.assertFalse(interval.disabled)
            self.assertEqual(interval.value, "100")
            frame(2, 2)
            self.assertEqual(board.snapshot.score, 2)
            frame(3, 3)
            self.assertEqual(board.snapshot.score, 2)
            # Toggling the filter must not reset the run's record, including
            # records received while local frame sampling hid their boards.
            checkbox.value = True
            await pilot.pause()
            self.assertEqual(board.snapshot.score, 3)
            record = board.snapshot
            frame(4, 3)
            self.assertEqual(board.snapshot, record)
            frame(4, 4)
            self.assertEqual(board.snapshot.score, 4)
            app._show_run({"state": "running", "high_score": 5})
            frame(5, 5)
            self.assertEqual(board.snapshot.score, 5)
            self.assertEqual(str(app.query_one("#score", Label).render()),
                             "Score: 5  High: 5")
            complete(6, 1, 5)
            self.assertEqual(str(app.query_one("#score", Label).render()),
                             "Score: 5  High: 5")
            self.assertEqual(control.operations, [])

    async def test_loads_and_submits_a_local_config_file(self) -> None:
        control = FakeControlClient()
        app = SnakeLabClient(
            telemetry_port=59999, control_client=control
        )
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "simulation.json"
            config_path.write_text('{"epochs": 100}', encoding="utf-8")

            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertTrue(await pilot.click("#submit-config"))
                await pilot.pause()
                app.screen.query_one("#config-path", Input).value = str(
                    config_path
                )
                await pilot.click("#config-submit")
                for _ in range(3):
                    await pilot.pause()

                self.assertIn(
                    ("submit", {"epochs": 100}), control.operations
                )
                self.assertEqual(app._active_run, "submitted-run-1")
                self.assertEqual(app._run_state, "queued")

        self.assertTrue(control.closed)

    async def test_live_messages_update_board_and_status_panes(self) -> None:
        control = FakeControlClient()
        app = SnakeLabClient(
            telemetry_port=59999, control_client=control
        )
        async with app.run_test(size=(120, 40)) as pilot:
            app.post_message(
                TelemetryReceived(
                    TOPIC_RUN,
                    TelemetryEnvelope(
                        0,
                        "run-1234567890",
                        {
                            "state": "running",
                            "epochs": 100,
                            "completed_epochs": 0,
                            "high_score": 0,
                            "move_delay_ms": 0,
                            "runtime": "Simulation running on GPU",
                        },
                    ),
                )
            )
            frame = FrameTelemetry(
                episode=12,
                step=7,
                action=1,
                reward=0.1,
                done=False,
                outcome=Outcome.EMPTY,
                board=BoardSnapshot(
                    width=8,
                    height=4,
                    snake_head=(4, 2),
                    snake_body=((3, 2), (2, 2)),
                    food=(7, 3),
                    direction=(1, 0),
                    score=3,
                ),
            )
            app.post_message(
                TelemetryReceived(
                    TOPIC_FRAME,
                    TelemetryEnvelope(0, "run-1234567890", frame.to_dict()),
                )
            )
            app.post_message(
                TelemetryReceived(
                    TOPIC_EPISODE,
                    TelemetryEnvelope(
                        0,
                        "run-1234567890",
                        {
                            "episode": {
                                "episode": 12,
                                "score": 3,
                                "epsilon": 0.5,
                                "loss": 0.125,
                                "outcome": "wall",
                            },
                            "summary": {
                                "epochs": 100,
                                "completed_epochs": 12,
                                "high_score": 5,
                            },
                        },
                    ),
                )
            )
            await pilot.pause()

            board = app.query_one("#board", SnakeBoard)
            self.assertEqual(board.snapshot, frame.board)
            self.assertIn(
                "12/100", str(app.query_one("#progress", Label).content)
            )
            self.assertIn(
                "0.5000", str(app.query_one("#epsilon", Label).content)
            )
            self.assertIn(
                "0.125000", str(app.query_one("#loss", Label).content)
            )
            self.assertFalse(
                app.query_one("#pause-resume", Button).disabled
            )

        self.assertTrue(control.closed)

    async def test_runtime_controls_call_the_async_client(self) -> None:
        control = FakeControlClient()
        app = SnakeLabClient(
            telemetry_port=59999, control_client=control
        )
        async with app.run_test(size=(120, 45)) as pilot:
            app.post_message(
                TelemetryReceived(
                    TOPIC_RUN,
                    TelemetryEnvelope(
                        0,
                        "run-1234567890",
                        {
                            "state": "running",
                            "epochs": 100,
                            "completed_epochs": 12,
                            "high_score": 5,
                            "move_delay_ms": 0,
                        },
                    ),
                )
            )
            await pilot.pause()

            await pilot.click("#pause-resume")
            await pilot.pause()
            self.assertEqual(app._run_state, "paused")
            self.assertEqual(
                app.query_one("#pause-resume", Button).label.plain,
                "Resume",
            )

            await pilot.click("#pause-resume")
            await pilot.pause()
            self.assertEqual(app._run_state, "running")

            app.query_one("#move-delay", Select).value = 100
            await pilot.pause()
            self.assertEqual(app._move_delay_ms, 100)
            self.assertIn(
                "Every move",
                str(app.query_one("#diagnostic-mode", Label).content),
            )

            await pilot.click("#cancel-run")
            await pilot.pause()
            await pilot.click("#confirm-cancel")
            await pilot.pause()
            self.assertEqual(app._run_state, "cancelling")

        self.assertEqual(
            control.operations,
            [
                ("pause", "run-1234567890"),
                ("resume", "run-1234567890"),
                ("delay", "run-1234567890", 100),
                ("cancel", "run-1234567890"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
