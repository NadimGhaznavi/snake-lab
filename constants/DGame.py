"""Snake game defaults and fixed observation dimensions."""

from typing import Final


class DGameDef:
    """Defaults for the Snake environment."""

    BOARD_WIDTH: Final[int] = 20
    BOARD_HEIGHT: Final[int] = 20
    INITIAL_SNAKE_LENGTH: Final[int] = 3
    MAX_MOVES_MULTIPLIER: Final[int] = 100
    OBSERVATION_RADIUS: Final[int] = 3
    OBSERVATION_SIZE: Final[int] = (
        (OBSERVATION_RADIUS * 2 + 1) ** 2 + 2
    )

    FOOD_REWARD: Final[float] = 10.0
    WALL_REWARD: Final[float] = -10.0
    SNAKE_REWARD: Final[float] = -10.0
    MAX_MOVES_REWARD: Final[float] = -10.0
    EMPTY_REWARD: Final[float] = 0.0
    CLOSER_TO_FOOD_REWARD: Final[float] = 0.1
    FURTHER_FROM_FOOD_REWARD: Final[float] = -0.1
