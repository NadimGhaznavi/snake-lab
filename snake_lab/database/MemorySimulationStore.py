"""In-memory simulation storage for tests and ephemeral runs."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, TYPE_CHECKING

from snake_lab.database.DBHelper import config_hash

if TYPE_CHECKING:
    from snake_lab.server.Simulator import EpisodeResult


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
            "config": deepcopy(config),
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

