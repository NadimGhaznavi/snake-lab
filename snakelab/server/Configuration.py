"""Public interface for constructing valid Snake Lab configurations."""

import json
import math
from functools import cache
from pathlib import Path
from typing import Any

from snakelab.server.JSONValidator import JSONValidationError, JSONValidator


DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "simulation-config-v2.schema.json"
)


class ConfigurationError(ValueError):
    """A submitted simulation configuration is invalid."""


class Configuration:
    """Resolve schema defaults and enforce Snake Lab configuration rules."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self._validator = JSONValidator(schema)

    @classmethod
    def from_file(cls, path: Path) -> "Configuration":
        with path.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        if not isinstance(schema, dict):
            raise TypeError("Configuration schema must be a JSON object")
        return cls(schema)

    def resolve(self, submitted: Any) -> dict[str, Any]:
        """Return a complete validated configuration without changing input."""
        try:
            resolved = self._validator.resolve(submitted)
        except JSONValidationError as error:
            raise ConfigurationError(str(error)) from error
        epsilon = resolved.get("epsilon")
        if (
            isinstance(epsilon, dict)
            and epsilon.get("minimum", 0) > epsilon.get("initial", 1)
        ):
            raise ConfigurationError(
                "$.epsilon.minimum: cannot exceed initial epsilon"
            )

        game = resolved.get("game", {})
        for name, value in game.get("rewards", {}).items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ConfigurationError(f"$.game.rewards.{name}: must be finite")
        initial_length = game.get("initial_snake_length")
        width = game.get("board_width")
        height = game.get("board_height")
        if isinstance(initial_length, int) and isinstance(width, int):
            if initial_length > width:
                raise ConfigurationError(
                    "$.game.initial_snake_length: cannot exceed board width"
                )
        if (
            isinstance(initial_length, int)
            and isinstance(width, int)
            and isinstance(height, int)
            and initial_length >= width * height
        ):
            raise ConfigurationError(
                "$.game.initial_snake_length: board must have room for food"
            )

        training = resolved.get("training", {})
        model = resolved.get("model", {})
        for path, value in (
            ("$.model.dropout", model.get("dropout")),
            ("$.training.tau", training.get("tau")),
        ):
            if isinstance(value, float) and not math.isfinite(value):
                raise ConfigurationError(f"{path}: must be finite")
        if model.get("type") == "transformer":
            hidden_size, heads = model.get("hidden_size"), model.get("heads")
            if isinstance(hidden_size, int) and isinstance(heads, int) and (
                heads <= 0 or hidden_size % heads
            ):
                raise ConfigurationError(
                    "$.model.heads: must be positive and divide hidden_size"
                )
        sequence_length = training.get("sequence_length")
        batch_size = training.get("batch_size")
        replay_max_frames = training.get("replay_max_frames")
        if all(
            isinstance(value, int)
            for value in (sequence_length, batch_size, replay_max_frames)
        ) and replay_max_frames < sequence_length * batch_size:
            raise ConfigurationError(
                "$.training.replay_max_frames: must hold at least one "
                "complete training batch"
            )
        return resolved


@cache
def simulation_config_template() -> Configuration:
    """Load and cache the current Snake Lab configuration schema."""
    return Configuration.from_file(DEFAULT_SCHEMA_PATH)
