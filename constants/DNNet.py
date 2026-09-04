"""Neural-network defaults and fixed dimensions."""

from typing import Final

from constants.DGame import DGameDef


class DNetDef:
    """
    Neural network constants.
    """

    OUTPUT_SIZE: Final[int] = DGameDef.ACTION_COUNT
    INPUT_SIZE: Final[int] = DGameDef.OBSERVATION_SIZE
