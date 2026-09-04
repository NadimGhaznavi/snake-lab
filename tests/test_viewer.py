import unittest

from textual.widgets import Label

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
from snake_lab.viewer import SnakeLabViewer, TelemetryReceived


class SnakeLabViewerTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_messages_update_board_and_status_panes(self) -> None:
        app = SnakeLabViewer(telemetry_port=59999)
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


if __name__ == "__main__":
    unittest.main()
