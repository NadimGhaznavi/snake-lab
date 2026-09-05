"""Construction and validation of SnakeLab simulation configurations."""

import json
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "simulation-config-v1.schema.json"
)


class ConfigurationError(ValueError):
    """A submitted simulation configuration is invalid."""


class ConfigTemplate:
    """Construct and validate configurations from a JSON Schema template."""

    def __init__(self, schema: dict[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._schema = deepcopy(schema)
        self._validator = Draft202012Validator(self._schema)

    @classmethod
    def from_file(cls, path: Path) -> "ConfigTemplate":
        with path.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        if not isinstance(schema, dict):
            raise TypeError("Configuration schema must be a JSON object")
        return cls(schema)

    @staticmethod
    def _defaults(schema: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for name, property_schema in schema.get("properties", {}).items():
            if "default" in property_schema:
                defaults[name] = deepcopy(property_schema["default"])
            elif property_schema.get("type") == "object":
                nested = ConfigTemplate._defaults(property_schema)
                if nested:
                    defaults[name] = nested
        return defaults

    @staticmethod
    def _merge(target: dict[str, Any], overrides: dict[str, Any]) -> None:
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                ConfigTemplate._merge(target[key], value)
            else:
                target[key] = deepcopy(value)

    @staticmethod
    def _error_path(error: Any) -> str:
        path = "$"
        for element in error.absolute_path:
            if isinstance(element, int):
                path += f"[{element}]"
            else:
                path += f".{element}"
        return path

    def resolve(self, submitted: Any) -> dict[str, Any]:
        """Apply defaults and validate a submitted JSON configuration."""
        if not isinstance(submitted, dict):
            raise ConfigurationError("$: config must be an object")

        resolved = self._defaults(self._schema)
        self._merge(resolved, submitted)
        errors = sorted(
            self._validator.iter_errors(resolved),
            key=lambda error: tuple(map(str, error.absolute_path)),
        )
        if errors:
            error = errors[0]
            raise ConfigurationError(
                f"{self._error_path(error)}: {error.message}"
            )
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
        min_episodes = training.get("replay_min_episodes")
        batch_size = training.get("batch_size")
        replay_max_frames = training.get("replay_max_frames")
        if all(
            isinstance(value, int)
            for value in (sequence_length, min_episodes, batch_size, replay_max_frames)
        ) and replay_max_frames < sequence_length * max(min_episodes, batch_size):
            raise ConfigurationError(
                "$.training.replay_max_frames: must hold sequence_length * "
                "max(batch_size, replay_min_episodes)"
            )
        return resolved


@cache
def simulation_config_template() -> ConfigTemplate:
    """Load and cache the current simulation configuration template."""
    return ConfigTemplate.from_file(DEFAULT_SCHEMA_PATH)
