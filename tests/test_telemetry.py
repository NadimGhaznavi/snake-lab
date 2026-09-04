import unittest

from snake_lab.game import (
    Direction,
    GameState,
    Outcome,
    Position,
    StepResult,
)
from snake_lab.protocol import ProtocolError
from snake_lab.telemetry import (
    BoardSnapshot,
    FrameTelemetry,
    TelemetryEnvelope,
)


class TelemetryContractTests(unittest.TestCase):
    def test_board_snapshot_round_trip_supports_rectangles(self) -> None:
        snapshot = BoardSnapshot(
            width=8,
            height=4,
            snake_head=(4, 2),
            snake_body=((3, 2), (2, 2)),
            food=(7, 3),
            direction=(1, 0),
            score=5,
        )

        self.assertEqual(
            BoardSnapshot.from_dict(snapshot.to_dict()), snapshot
        )

    def test_board_snapshot_supports_completed_board_without_food(self) -> None:
        snapshot = BoardSnapshot(
            width=2,
            height=2,
            snake_head=(1, 0),
            snake_body=((0, 0), (0, 1), (1, 1)),
            food=None,
            direction=(1, 0),
            score=1,
        )

        restored = BoardSnapshot.from_dict(snapshot.to_dict())

        self.assertIsNone(restored.food)
        self.assertEqual(restored, snapshot)

    def test_frame_is_constructed_from_one_coherent_game_state(self) -> None:
        state = GameState(
            snake_head=Position(3, 2),
            snake_body=(Position(2, 2), Position(1, 2)),
            direction=Direction.right(),
            food_position=Position(4, 4),
            score=2,
            move_count=9,
            grid_size=(7, 5),
            seed=7,
            episode_id=3,
        )
        result = StepResult(
            new_state=state,
            observation=state.observation(),
            reward=0.1,
            outcome=Outcome.EMPTY,
            done=False,
        )

        frame = FrameTelemetry.from_step(
            episode=3, action=1, result=result
        )

        self.assertEqual(FrameTelemetry.from_dict(frame.to_dict()), frame)
        self.assertEqual(frame.board.score, 2)
        self.assertEqual(frame.step, 9)

    def test_telemetry_envelope_round_trip_is_strict(self) -> None:
        envelope = TelemetryEnvelope(
            sequence=4,
            run_id="run-1",
            payload={"state": "running"},
        )
        self.assertEqual(
            TelemetryEnvelope.from_dict(envelope.to_dict()), envelope
        )

        malformed = envelope.to_dict()
        malformed["extra"] = True
        with self.assertRaises(ProtocolError):
            TelemetryEnvelope.from_dict(malformed)


if __name__ == "__main__":
    unittest.main()
