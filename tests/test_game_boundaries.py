"""Game parsing errors stay independent of the messaging protocol."""

import ast
from copy import deepcopy
from pathlib import Path
import unittest

from constants.DGame import Outcome
from snake_lab.game.BoardSnapshot import BoardSnapshot, BoardSnapshotError
from snake_lab.zmq.FrameTelemetry import FrameTelemetry
from snake_lab.zmq.Protocol import ProtocolError


class GameBoundaryTests(unittest.TestCase):
    def test_snapshot_errors_are_translated_only_at_frame_boundary(self):
        board = BoardSnapshot(20, 20, (10, 10), ((9, 10), (8, 10)),
                              (15, 10), (1, 0), 0).to_dict()
        malformed = [None, {**board, "extra": 1}, {**board, "grid_size": [0, 20]},
                     {**board, "snake_body": None}, {**board, "score": True},
                     {**board, "snake_head": [1.0, 2]}]
        for data in malformed:
            with self.subTest(data=data):
                with self.assertRaises(BoardSnapshotError) as game_error:
                    BoardSnapshot.from_dict(data)
                self.assertNotIsInstance(game_error.exception, ProtocolError)
                frame = {"episode": 1, "step": 1, "action": 1, "reward": 0.0,
                         "done": False, "outcome": Outcome.EMPTY.value, "board": data}
                with self.assertRaises(ProtocolError) as wire_error:
                    FrameTelemetry.from_dict(frame)
                self.assertEqual(wire_error.exception.code, "invalid_telemetry")
                self.assertEqual(str(wire_error.exception), str(game_error.exception))
                self.assertIsInstance(wire_error.exception.__cause__, BoardSnapshotError)

    def test_game_has_no_application_or_transport_imports(self):
        folder = Path(__file__).resolve().parents[1] / "snake_lab/game"
        forbidden = ("snake_lab.zmq", "snake_lab.server", "snake_lab.client",
                     "snake_lab.database", "snake_lab.nn")
        for path in folder.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                           else [alias.name for alias in node.names] if isinstance(node, ast.Import)
                           else [])
                for module in modules:
                    self.assertFalse(module.startswith(forbidden), (path.name, module))

    def test_valid_frame_wire_format_is_unchanged(self):
        board = BoardSnapshot(20, 20, (10, 10), ((9, 10), (8, 10)),
                              (15, 10), (1, 0), 0)
        frame = FrameTelemetry(1, 2, 1, 0.0, False, Outcome.EMPTY, board)
        data = frame.to_dict()
        before = deepcopy(data)
        self.assertEqual(FrameTelemetry.from_dict(data), frame)
        self.assertEqual(data, before)
