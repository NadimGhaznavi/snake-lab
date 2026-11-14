"""Recurrent neural-network model for Snake Lab."""

import torch
import torch.nn as nn

from snakelab.constants.DSnakeLab import DSnakeLab
from snakelab.nn.SequenceModel import SequenceModel
from snakelab.utils.MyLog import MyLog


class RNNModel(SequenceModel):
    """Map ordered game-state sequences to action values."""

    def __init__(
        self,
        *,
        seed: int,
        hidden_size: int,
        dropout: float,
        layers: int,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        super().__init__(
            seed=seed, hidden_size=hidden_size, dropout=dropout, layers=layers,
            log_file=log_file, log=log,
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

    def _encode_sequence(self, states: torch.Tensor) -> torch.Tensor:
        projected = self.input_layer(states)
        recurrent, _ = self.recurrent_layer(projected)
        return recurrent

    def reset_parameters(self) -> None:
        """Reset all trainable layers."""
        for module in self.modules():
            if isinstance(module, (nn.Linear, nn.RNN)):
                module.reset_parameters()
