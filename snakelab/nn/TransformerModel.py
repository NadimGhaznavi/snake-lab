"""Causal PyTorch Transformer over a rolling sequence of game observations."""

import math

import torch
from torch import nn

from snakelab.constants.DSnakeLab import DSnakeLab
from snakelab.nn.SequenceModel import SequenceModel
from snakelab.utils.MyLog import MyLog


class TransformerModel(SequenceModel):
    """Predict action values using positional encoding and causal attention."""

    def __init__(
        self, *, seed: int, hidden_size: int, dropout: float, layers: int,
        heads: int, max_sequence_length: int,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        super().__init__(
            seed=seed, hidden_size=hidden_size, dropout=dropout, layers=layers,
            log_file=log_file, log=log,
        )
        if type(heads) is not int or heads <= 0 or hidden_size % heads:
            raise ValueError("heads must be positive and divide hidden_size")
        if type(max_sequence_length) is not int or max_sequence_length <= 0:
            raise ValueError("max_sequence_length must be a positive integer")
        self.heads = heads
        self.max_sequence_length = max_sequence_length

        self.input_layer = nn.Linear(self.input_size, hidden_size)
        layer = nn.TransformerEncoderLayer(
            d_model=hidden_size, nhead=heads, dim_feedforward=4 * hidden_size,
            dropout=self.dropout, batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer, num_layers=layers, norm=nn.LayerNorm(hidden_size),
            enable_nested_tensor=False,
        )
        self.output_layer = nn.Linear(hidden_size, self.output_size)

        positions = torch.arange(max_sequence_length, dtype=torch.float32)[:, None]
        frequencies = torch.exp(
            torch.arange(0, hidden_size, 2, dtype=torch.float32)
            * (-math.log(10000.0) / hidden_size)
        )
        encoding = torch.zeros(max_sequence_length, hidden_size)
        encoding[:, 0::2] = torch.sin(positions * frequencies)
        encoding[:, 1::2] = torch.cos(positions * frequencies[:hidden_size // 2])
        self.register_buffer("position_encoding", encoding, persistent=False)
        self.register_buffer(
            "causal_mask",
            torch.ones(max_sequence_length, max_sequence_length, dtype=torch.bool).triu_(1),
            persistent=False,
        )
        # TransformerEncoder clones its prototype; initialize each layer separately.
        self.reset_parameters()
        self.log.info(
            f"Initialized Transformer model: hidden={hidden_size}, "
            f"layers={layers}, heads={heads}, dropout={self.dropout}"
        )

    def _encode_sequence(self, states: torch.Tensor) -> torch.Tensor:
        length = states.shape[1]
        if length > self.max_sequence_length:
            raise ValueError(f"sequence length cannot exceed {self.max_sequence_length}")
        embedded = self.input_layer(states) + self.position_encoding[:length]
        return self.encoder(
            embedded, mask=self.causal_mask[:length, :length], is_causal=True,
        )

    def reset_parameters(self) -> None:
        """Initialize independent attention/feedforward weights and layer norms."""
        for name, parameter in self.named_parameters():
            if parameter.dim() > 1:
                nn.init.xavier_uniform_(parameter)
            elif name.endswith("weight"):
                nn.init.ones_(parameter)
            else:
                nn.init.zeros_(parameter)
