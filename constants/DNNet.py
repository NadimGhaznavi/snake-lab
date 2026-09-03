"""Neural-network defaults and fixed dimensions."""

from typing import Final

from constants.DGame import DGameDef


class DNetDef:
    """
    Neural network constants.
    """

    MOVE_DELAY: Final[float] = 0.02
    OUTPUT_SIZE: Final[int] = 3
    PER_STEP: Final[bool] = True
    INPUT_SIZE: Final[int] = DGameDef.OBSERVATION_SIZE


class DRNN:
    """
    RNN Model defaults
    """

    BATCH_SIZE: Final[int] = 64
    CLOSER_TO_FOOD: Final[float] = 0.1
    DROPOUT_P_VALUE: Final[float] = 0.1
    EMPTY_MOVE_REWARD: Final[float] = 0.0
    FURTHER_FROM_FOOD: Final[float] = -0.1
    GAMMA: Final[float] = 0.96
    HIDDEN_SIZE: Final[int] = 192
    LEARNING_RATE: Final[float] = 0.002
    RNN_LAYERS: Final[int] = 3
    SEQ_LENGTH: Final[int] = 4
    TAU: Final[float] = 0.001
