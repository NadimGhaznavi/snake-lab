"""Persistence for SnakeLab simulation runs and episode results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

import pymysql

from constants.DSnakeLab import DSnakeLab

if TYPE_CHECKING:
    from snake_lab.simulator import EpisodeResult


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
    ) -> None: ...

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
    ) -> None:
        run = self.runs[run_id]
        run["status"] = status
        run["episode_count"] = episode_count
        run["high_score"] = high_score
        run["error_message"] = error_message

    def close(self) -> None:
        pass


class MariaDBSimulationStore:
    """Transactional MariaDB implementation of simulation persistence."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @classmethod
    def connect(
        cls,
        credentials_file: str | Path = DSnakeLab.DB_CREDENTIALS_FILE,
    ) -> MariaDBSimulationStore:
        path = Path(credentials_file)
        with path.open(encoding="utf-8") as credential_stream:
            credentials = json.load(credential_stream)
        password = credentials.get("password")
        if not isinstance(password, str) or not password:
            raise ValueError(
                f"Database password is missing from {credentials_file}"
            )

        connection = pymysql.connect(
            host=DSnakeLab.DB_HOST,
            port=DSnakeLab.DB_PORT,
            user=DSnakeLab.DB_USER,
            password=password,
            database=DSnakeLab.DB_NAME,
            charset="utf8mb4",
            autocommit=False,
            init_command="SET time_zone = '+00:00'",
            cursorclass=pymysql.cursors.DictCursor,
        )
        store = cls(connection)
        store._recover_interrupted_runs()
        return store

    def _recover_interrupted_runs(self) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE simulation_runs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP(6),
                    error_message = 'Server stopped before run completed'
                WHERE status IN ('queued', 'running', 'paused', 'cancelling')
                """
            )
        self._connection.commit()

    def create_run(
        self,
        run_id: str,
        config: dict[str, Any],
        project_version: str,
    ) -> None:
        digest = config_hash(config)
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO simulation_runs (
                        run_id, project_version, config, config_hash, status
                    ) VALUES (%s, %s, %s, %s, 'queued')
                    """,
                    (
                        run_id,
                        project_version,
                        canonical_config(config),
                        digest,
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def mark_started(self, run_id: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE simulation_runs
                SET status = 'running',
                    started_at = CURRENT_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (run_id,),
            )
        self._connection.commit()

    def set_status(self, run_id: str, status: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE simulation_runs SET status = %s WHERE run_id = %s",
                (status, run_id),
            )
        self._connection.commit()

    def record_episode(
        self,
        run_id: str,
        result: EpisodeResult,
        episode_count: int,
        high_score: int,
    ) -> None:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO simulation_episodes (
                        run_id, episode, score, steps, epsilon, loss
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        result.episode,
                        result.score,
                        result.steps,
                        result.epsilon,
                        result.loss,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE simulation_runs
                    SET episode_count = %s, high_score = %s
                    WHERE run_id = %s
                    """,
                    (episode_count, high_score, run_id),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def finish_run(
        self,
        run_id: str,
        status: str,
        episode_count: int,
        high_score: int,
        error_message: str | None = None,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE simulation_runs
                SET status = %s,
                    episode_count = %s,
                    high_score = %s,
                    completed_at = CURRENT_TIMESTAMP(6),
                    error_message = %s
                WHERE run_id = %s
                """,
                (
                    status,
                    episode_count,
                    high_score,
                    error_message,
                    run_id,
                ),
            )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
