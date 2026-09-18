"""Internal JSON Schema helper for Configuration."""

from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator


class JSONValidationError(ValueError):
    """A document does not satisfy its JSON Schema."""


class JSONValidator:
    """Apply schema defaults and validate documents without application rules."""

    def __init__(self, schema: dict[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._schema = deepcopy(schema)
        self._validator = Draft202012Validator(self._schema)

    @staticmethod
    def _defaults(schema: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for name, property_schema in schema.get("properties", {}).items():
            if "default" in property_schema:
                defaults[name] = deepcopy(property_schema["default"])
            elif property_schema.get("type") == "object":
                nested = JSONValidator._defaults(property_schema)
                if nested:
                    defaults[name] = nested
        return defaults

    @staticmethod
    def _merge(target: dict[str, Any], overrides: dict[str, Any]) -> None:
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                JSONValidator._merge(target[key], value)
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
            raise JSONValidationError("$: config must be an object")

        resolved = self._defaults(self._schema)
        self._merge(resolved, submitted)
        errors = sorted(
            self._validator.iter_errors(resolved),
            key=lambda error: tuple(map(str, error.absolute_path)),
        )
        if errors:
            error = errors[0]
            raise JSONValidationError(
                f"{self._error_path(error)}: {error.message}"
            )
        return resolved
