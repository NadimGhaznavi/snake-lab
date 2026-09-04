import unittest

from textual.app import App, ComposeResult

from snake_lab.board import SnakeBoard
from snake_lab.telemetry import BoardSnapshot


class BoardTestApp(App[None]):
    def compose(self) -> ComposeResult:
        yield SnakeBoard(width=8, height=4, id="board")


class SnakeBoardTests(unittest.IsolatedAsyncioTestCase):
    async def test_atomic_snapshot_updates_rectangular_board(self) -> None:
        app = BoardTestApp()
        async with app.run_test(size=(30, 10)) as pilot:
            board = app.query_one("#board", SnakeBoard)
            snapshot = BoardSnapshot(
                width=8,
                height=4,
                snake_head=(4, 2),
                snake_body=((3, 2), (2, 2)),
                food=(7, 3),
                direction=(1, 0),
                score=5,
            )

            board.apply_snapshot(snapshot)
            await pilot.pause()

            self.assertIs(board.snapshot, snapshot)
            self.assertEqual(board.virtual_size.width, 16)
            self.assertEqual(board.virtual_size.height, 4)
            self.assertEqual(board.render_line(2).cell_length, 16)

    async def test_terminal_snapshot_without_food_renders(self) -> None:
        app = BoardTestApp()
        async with app.run_test(size=(20, 8)) as pilot:
            board = app.query_one("#board", SnakeBoard)
            board.apply_snapshot(
                BoardSnapshot(
                    width=2,
                    height=2,
                    snake_head=(1, 0),
                    snake_body=((0, 0), (0, 1), (1, 1)),
                    food=None,
                    direction=(1, 0),
                    score=1,
                )
            )
            await pilot.pause()

            self.assertEqual(board.render_line(0).cell_length, 4)


if __name__ == "__main__":
    unittest.main()
