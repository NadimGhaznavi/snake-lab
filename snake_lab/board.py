"""Flicker-free Textual rendering for SnakeLab board snapshots."""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Offset, Region, Size
from textual.reactive import var
from textual.scroll_view import ScrollView
from textual.strip import Strip

from snake_lab.telemetry import BoardSnapshot


class SnakeBoard(ScrollView):
    """Render a board line-by-line and invalidate only changed cells."""

    COMPONENT_CLASSES = {
        "snakeboard--empty-a",
        "snakeboard--empty-b",
        "snakeboard--food",
        "snakeboard--snake",
        "snakeboard--snake-head",
    }

    DEFAULT_CSS = """
    SnakeBoard > .snakeboard--empty-a {
        background: #111111;
    }
    SnakeBoard > .snakeboard--empty-b {
        background: #000000;
    }
    SnakeBoard > .snakeboard--food {
        background: #940101;
    }
    SnakeBoard > .snakeboard--snake {
        background: #025b02;
    }
    SnakeBoard > .snakeboard--snake-head {
        background: #16e116;
    }
    """

    snapshot = var(None)

    def __init__(
        self, width: int = 20, height: int = 20, *, id: str | None = None
    ) -> None:
        super().__init__(id=id)
        self._grid_width = width
        self._grid_height = height
        self.virtual_size = Size(width * 2, height)

    def apply_snapshot(self, snapshot: BoardSnapshot) -> None:
        if not isinstance(snapshot, BoardSnapshot):
            raise TypeError("snapshot must be a BoardSnapshot")
        self.snapshot = snapshot

    def _square_region(self, position: tuple[int, int]) -> Region:
        x, y = position
        region = Region(x * 2, y, 2, 1)
        return region.translate(-self.scroll_offset)

    @staticmethod
    def _occupied(snapshot: BoardSnapshot) -> set[tuple[int, int]]:
        occupied = {snapshot.snake_head, *snapshot.snake_body}
        if snapshot.food is not None:
            occupied.add(snapshot.food)
        return occupied

    def watch_snapshot(
        self,
        previous: BoardSnapshot | None,
        current: BoardSnapshot | None,
    ) -> None:
        if current is None:
            self.refresh()
            return

        dimensions_changed = (
            previous is None
            or previous.width != current.width
            or previous.height != current.height
        )
        self._grid_width = current.width
        self._grid_height = current.height
        if dimensions_changed:
            self.virtual_size = Size(current.width * 2, current.height)
            self.refresh(layout=True)
            return

        dirty = self._occupied(previous) | self._occupied(current)
        for position in dirty:
            self.refresh(self._square_region(position))

    def render_line(self, y: int) -> Strip:
        snapshot = self.snapshot
        if snapshot is None:
            return Strip.blank(
                self.size.width, self.visual_style.rich_style
            )

        scroll_x, scroll_y = self.scroll_offset
        row = y + scroll_y
        if row < 0 or row >= self._grid_height:
            return Strip.blank(
                self.size.width, self.visual_style.rich_style
            )

        empty_a = self.get_component_rich_style("snakeboard--empty-a")
        empty_b = self.get_component_rich_style("snakeboard--empty-b")
        food = self.get_component_rich_style("snakeboard--food")
        snake = self.get_component_rich_style("snakeboard--snake")
        snake_head = self.get_component_rich_style(
            "snakeboard--snake-head"
        )
        body = set(snapshot.snake_body)

        def square_style(column: int) -> Style:
            position = (column, row)
            if snapshot.food == position:
                return food
            if snapshot.snake_head == position:
                return snake_head
            if position in body:
                return snake
            return empty_a if (column + row) % 2 else empty_b

        segments = [
            Segment("  ", square_style(column))
            for column in range(self._grid_width)
        ]
        strip = Strip(segments, self._grid_width * 2)
        return strip.crop(scroll_x, scroll_x + self.size.width)
