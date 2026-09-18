"""Public interface for constructing valid SnakeLab configurations."""

import json
from functools import cache
from pathlib import Path
from typing import Any

from snake_lab.server.JSONValidator import JSONValidationError, JSONValidator


DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "simulation-config-v2.schema.json"
)


class ConfigurationError(ValueError):
    """A submitted simulation configuration is invalid."""


class Configuration:
    """Resolve schema defaults and enforce SnakeLab configuration rules."""

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
    """Load and cache the current SnakeLab configuration schema."""
    return Configuration.from_file(DEFAULT_SCHEMA_PATH)
