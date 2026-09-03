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
        return resolved


@cache
def simulation_config_template() -> ConfigTemplate:
    """Load and cache the current simulation configuration template."""
    return ConfigTemplate.from_file(DEFAULT_SCHEMA_PATH)
