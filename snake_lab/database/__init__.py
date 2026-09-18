"""Persistence for SnakeLab simulation runs and episode results."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from snake_lab.server.Simulator import EpisodeResult


# Stable SQL column order, matching database-v3.sql.
CONFIGURATION_PATHS = (
    "epochs",
    "seed",
    "game.board_width",
    "game.board_height",
    "game.initial_snake_length",
    "game.max_moves_multiplier",
    "game.rewards.food",
    "game.rewards.wall",
    "game.rewards.snake",
    "game.rewards.max_moves",
    "game.rewards.empty",
    "game.rewards.closer_to_food",
    "game.rewards.further_from_food",
    "model.hidden_size",
    "model.layers",
    "model.dropout",
    "training.sequence_length",
    "training.batch_size",
    "training.replay_max_frames",
    "training.learning_rate",
    "training.gamma",
    "training.tau",
    "training.max_gradient_norm",
    "epsilon.initial",
    "epsilon.minimum",
    "epsilon.decay",
)


def configuration_values(config: dict[str, Any]) -> tuple[Any, ...]:
    """Flatten a resolved runtime configuration without changing its values."""
    values = []
    for path in CONFIGURATION_PATHS:
        value: Any = config
        for key in path.split("."):
            value = value[key]
        values.append(value)
    return tuple(values)


class SimulationStore(Protocol):
    """Persistence operations required by the serial simulation worker."""

    def create_run(
        self,
        run_id: str,
        config: dict[str, Any],
        project_version: str,
    ) -> None: ...

    def mark_started(self, run_id: str) -> None: ...

    def set_status(self, run_id: str, status: str) -> None: ...

    def record_episode(
        self,
        run_id: str,
        result: EpisodeResult,
        episode_count: int,
        high_score: int,
    ) -> None: ...

    def finish_run(
        self,
        run_id: str,
        status: str,
        episode_count: int,
        high_score: int,
        error_message: str | None = None,
        high_score_snapshot: dict[str, Any] | None = None,
    ) -> None: ...

    def get_high_score_snapshot(self, run_id: str) -> dict[str, Any] | None: ...

    def close(self) -> None: ...


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


class MemorySimulationStore:
    """Ephemeral store used by unit tests and explicit development runs."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.episodes: dict[str, list[EpisodeResult]] = {}

    def create_run(
        self,
        run_id: str,
        config: dict[str, Any],
        project_version: str,
    ) -> None:
        if run_id in self.runs:
            raise ValueError(f"Run ID already exists: {run_id}")
        self.runs[run_id] = {
            "run_id": run_id,
            "project_version": project_version,
            "config": config,
            "config_hash": config_hash(config),
            "status": "queued",
            "episode_count": None,
            "high_score": None,
            "high_score_snapshot": None,
            "error_message": None,
        }
        self.episodes[run_id] = []

    def mark_started(self, run_id: str) -> None:
        self.set_status(run_id, "running")

    def set_status(self, run_id: str, status: str) -> None:
        self.runs[run_id]["status"] = status

    def record_episode(
        self,
        run_id: str,
        result: EpisodeResult,
        episode_count: int,
        high_score: int,
    ) -> None:
        self.episodes[run_id].append(result)
        self.runs[run_id]["episode_count"] = episode_count
        self.runs[run_id]["high_score"] = high_score

    def finish_run(
        self,
        run_id: str,
        status: str,
        episode_count: int,
        high_score: int,
        error_message: str | None = None,
        high_score_snapshot: dict[str, Any] | None = None,
    ) -> None:
        run = self.runs[run_id]
        run["status"] = status
        run["episode_count"] = episode_count
        run["high_score"] = high_score
        run["error_message"] = error_message
        run["high_score_snapshot"] = (
            json.loads(json.dumps(high_score_snapshot, allow_nan=False))
            if high_score_snapshot is not None else None
        )

    def get_high_score_snapshot(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        return {
            "run_id": run_id,
            "high_score_snapshot": json.loads(json.dumps(run["high_score_snapshot"])),
        }

    def close(self) -> None:
        pass

