"""Deterministic Snake game state, rules, and environment."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snake_lab.game.GameState import GameState


class Action(IntEnum):
    """Actions relative to the snake's current direction."""

    LEFT = 0
    STRAIGHT = 1
    RIGHT = 2


class Outcome(StrEnum):
    """Result category for one attempted move."""

    EMPTY = "empty"
    FOOD = "food"
    WALL = "wall"
    SNAKE = "snake"
    MAX_MOVES = "max_moves"
    BOARD_FILLED = "board_filled"


@dataclass(frozen=True, slots=True)
class Position:
    """One integer coordinate on the board."""

    x: int
    y: int


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


@dataclass(frozen=True, slots=True)
class RewardConfig:
    """Rewards applied by the game rules."""

    food: float
    wall: float
    snake: float
    max_moves: float
    empty: float
    closer_to_food: float
    further_from_food: float

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} reward must be numeric")
            object.__setattr__(self, name, float(value))


@dataclass(frozen=True, slots=True)
class StepResult:
    """State and reinforcement signal produced by one move."""

    new_state: GameState
    observation: tuple[float, ...]
    reward: float
    outcome: Outcome
    done: bool

    @property
    def is_collision(self) -> bool:
        return self.outcome in (Outcome.WALL, Outcome.SNAKE)


def _random_free_position(
    rng: random.Random,
    grid_size: tuple[int, int],
    occupied: set[Position],
) -> Position | None:
    width, height = grid_size
    free = [
        Position(x, y)
        for x in range(width)
        for y in range(height)
        if Position(x, y) not in occupied
    ]
    return rng.choice(free) if free else None
