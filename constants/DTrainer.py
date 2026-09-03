"""Trainer implementation defaults."""

import torch.nn as nn
import torch.optim as optim

from typing import Final


class DTrainer:
    CRITERION = nn.SmoothL1Loss
    OPTIM = optim.Adam
    TAU: Final[float] = 0.005
    UPDATE_FREQ: Final[int] = 100
