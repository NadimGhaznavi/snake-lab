import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from textual.widgets import Button, Input, Label, Select

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
            ):
                widget = app.query_one(selector)
                self.assertGreater(widget.region.height, 0)
                self.assertLessEqual(widget.region.bottom, app.size.height)

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
