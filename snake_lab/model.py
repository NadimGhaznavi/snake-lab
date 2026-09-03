"""Recurrent neural-network model for SnakeLab."""

import torch
import torch.nn as nn

from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from constants.DNNet import DNetDef, DRNN
from constants.DSnakeLab import DSnakeLab
from utils.MyLog import MyLog


class RNNModel(nn.Module):
    """Map ordered game-state sequences to action values."""

    def __init__(
        self,
        *,
        seed: int,
        hidden_size: int = DRNN.HIDDEN_SIZE,
        dropout: float = DRNN.DROPOUT_P_VALUE,
        layers: int = DRNN.RNN_LAYERS,
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
            client_id=DModule.RNN_MODEL,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=False,
        )

        self.input_layer = nn.Sequential(
            nn.Linear(self.input_size, self.hidden_size),
            nn.ReLU(),
        )
        self.recurrent_layer = nn.RNN(
            input_size=self.hidden_size,
            hidden_size=self.hidden_size,
            nonlinearity="tanh",
            num_layers=self.layers,
            dropout=self.dropout if self.layers > 1 else 0.0,
            batch_first=True,
        )
        self.output_layer = nn.Linear(self.hidden_size, self.output_size)
        self.log.info(
            f"Initialized RNN model: hidden={hidden_size}, "
            f"layers={layers}, dropout={self.dropout}"
        )

    def forward_sequence(self, states: torch.Tensor) -> torch.Tensor:
        """Return action values for every timestep as ``[B, T, A]``."""
        if states.dim() == 1:
            states = states.unsqueeze(0).unsqueeze(0)
        elif states.dim() == 2:
            states = states.unsqueeze(0)
        elif states.dim() != 3:
            raise ValueError("states must have one, two, or three dimensions")
        if states.shape[-1] != self.input_size:
            raise ValueError(f"states must have {self.input_size} features")

        projected = self.input_layer(states)
        recurrent, _ = self.recurrent_layer(projected)
        return self.output_layer(recurrent)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        """Return action values for the final timestep as ``[B, A]``."""
        return self.forward_sequence(states)[:, -1, :]

    def reset_parameters(self) -> None:
        """Reset all trainable layers."""
        for module in self.children():
            if hasattr(module, "reset_parameters"):
                module.reset_parameters()
                continue
            for child in module.children():
                if hasattr(child, "reset_parameters"):
                    child.reset_parameters()
