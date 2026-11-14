"""Epsilon-greedy implementation constants."""

from typing import Final


class DEpsilon:
    """Fixed behavior that is not part of the experiment schedule."""

    CUTOFF: Final[float] = 0.001
    NICE_ACTIVATION_THRESHOLD: Final[float] = 0.0001
