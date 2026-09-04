"""Snake game defaults and fixed observation dimensions."""

from typing import Final


class DGameDef:
    """Fixed dimensions shared by the game and neural network."""

    ACTION_COUNT: Final[int] = 3
    OBSERVATION_RADIUS: Final[int] = 3
    OBSERVATION_SIZE: Final[int] = (
        (OBSERVATION_RADIUS * 2 + 1) ** 2 + 2
    )
