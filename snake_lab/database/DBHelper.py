"""Shared configuration mapping and identity helpers for persistence."""

import hashlib
import json
from typing import Any

from constants.DSQL import DSQL


def configuration_values(config: dict[str, Any]) -> tuple[Any, ...]:
    """Flatten a resolved runtime configuration without changing its values."""
    values = []
    for path in DSQL.CONFIGURATION_PATHS:
        value: Any = config
        for key in path.split("."):
            value = value[key]
        values.append(value)
    return tuple(values)


def canonical_config(config: dict[str, Any]) -> str:
    """Serialize resolved configuration deterministically for storage."""
    return json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def config_hash(config: dict[str, Any]) -> str:
    """Return the SHA-256 identity of a resolved configuration."""
    encoded = canonical_config(config).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
