"""One cardinal movement vector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Direction:
    """One cardinal movement vector."""

    dx: int
    dy: int

    def __post_init__(self) -> None:
        if (self.dx, self.dy) not in {
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
        }:
            raise ValueError("direction must be a cardinal unit vector")

    @classmethod
    def left(cls) -> Direction:
        return cls(-1, 0)

    @classmethod
    def right(cls) -> Direction:
        return cls(1, 0)

    @classmethod
    def up(cls) -> Direction:
        return cls(0, -1)

    @classmethod
    def down(cls) -> Direction:
        return cls(0, 1)

    def turn_left(self) -> Direction:
        return Direction(self.dy, -self.dx)

    def turn_right(self) -> Direction:
        return Direction(-self.dy, self.dx)
