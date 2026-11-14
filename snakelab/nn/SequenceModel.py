"""Shared interface for action-value models over ordered observations."""

from abc import ABC, abstractmethod

import torch
from torch import nn

from snakelab.constants.DMyLog import DMyLogDef
from snakelab.constants.DNNet import DNetDef
from snakelab.constants.DSnakeLab import DSnakeLab
from snakelab.utils.MyLog import MyLog


class SequenceModel(nn.Module, ABC):
    """Accept [F], [T,F], or [B,T,F]; predict three relative action values."""

    output_layer: nn.Linear

    def __init__(
        self, *, seed: int, hidden_size: int, dropout: float, layers: int,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        super().__init__()
        if type(seed) is not int:
            raise TypeError("seed must be an integer")
        if type(hidden_size) is not int or hidden_size <= 0:
            raise ValueError("hidden_size must be a positive integer")
        if type(layers) is not int or layers <= 0:
            raise ValueError("layers must be a positive integer")
        if not isinstance(dropout, (int, float)) or not 0 <= dropout < 1:
            raise ValueError("dropout must be in the range [0, 1)")

        torch.manual_seed(seed)
        self.input_size = DNetDef.INPUT_SIZE
        self.output_size = DNetDef.OUTPUT_SIZE
        self.hidden_size = hidden_size
        self.layers = layers
        self.dropout = float(dropout)
        self.log = log or MyLog(
            client_id=type(self).__name__,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=False,
        )

    def _as_sequence(self, states: torch.Tensor) -> torch.Tensor:
        if states.dim() == 1:
            states = states.unsqueeze(0).unsqueeze(0)
        elif states.dim() == 2:
            states = states.unsqueeze(0)
        elif states.dim() != 3:
            raise ValueError("states must have one, two, or three dimensions")
        if states.shape[-1] != self.input_size:
            raise ValueError(f"states must have {self.input_size} features")
        if states.shape[1] == 0:
            raise ValueError("states must contain at least one timestep")
        return states

    @abstractmethod
    def _encode_sequence(self, states: torch.Tensor) -> torch.Tensor:
        """Encode normalized [B,T,F] observations as [B,T,H]."""

    def forward_sequence(self, states: torch.Tensor) -> torch.Tensor:
        """Return action values for every timestep as [B,T,A]."""
        return self.output_layer(self._encode_sequence(self._as_sequence(states)))

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        """Return final action values as [B,A], projecting only the last frame."""
        encoded = self._encode_sequence(self._as_sequence(states))
        return self.output_layer(encoded[:, -1, :])

    @abstractmethod
    def reset_parameters(self) -> None:
        """Reset every trainable parameter, retaining fixed sequence buffers."""
