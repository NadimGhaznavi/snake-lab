"""Snake game defaults and fixed observation dimensions."""

from enum import IntEnum, StrEnum
from typing import Final


class DGameDef:
    """Fixed dimensions shared by the game and neural network."""

    ACTION_COUNT: Final[int] = 3
    STATE_LENGTH_BITS: Final[int] = 7
    OBSERVATION_SIZE: Final[int] = 16 + STATE_LENGTH_BITS


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
