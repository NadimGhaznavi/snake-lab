"""Storage interface for simulation persistence."""

from __future__ import annotations

from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from snake_lab.server.Simulator import EpisodeResult


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

