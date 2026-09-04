"""Trainer implementation defaults."""

import torch.nn as nn
import torch.optim as optim


class DTrainer:
    CRITERION = nn.SmoothL1Loss
    OPTIM = optim.Adam
