"""SnakeLab persistence operations expressed through the generic database manager."""

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

from constants.DSnakeLab import DSnakeLab
from constants.DSQL import DSQL
from snake_lab.database.DBHelper import configuration_values, config_hash
from snake_lab.database.DbMgr import DbMgr, SqlValue

if TYPE_CHECKING:
    from snake_lab.server.Simulator import EpisodeResult


class SnakeDb:
    """Translate application requests into transactional database operations."""

    def __init__(self, dbmgr: DbMgr) -> None:
        self._dbmgr = dbmgr

    @classmethod
    def connect(cls, credentials_file: str | Path = DSnakeLab.DB_CREDENTIALS_FILE,
                *, host: str = DSnakeLab.DB_HOST, port: int = DSnakeLab.DB_PORT,
                connect_timeout: int = 3, read_timeout: int = 3,
                write_timeout: int = 3) -> "SnakeDb":
        return cls(DbMgr.connect(credentials_file=credentials_file, host=host, port=port,
                                 user=DSnakeLab.DB_USER, database=DSnakeLab.DB_NAME,
                                 connect_timeout=connect_timeout, read_timeout=read_timeout,
                                 write_timeout=write_timeout))

    def recover_interrupted_runs(self) -> None:
        """Called only by the server at startup, never by a client connection."""
        self._dbmgr.update("simulation_runs", {
            "status": "failed", "completed_at": SqlValue.CURRENT_TIMESTAMP,
            "error_message": "Server stopped before run completed",
        }, where={"status": ("queued", "running", "paused", "cancelling")})

    def create_run(self, run_id: str, config: dict[str, Any], project_version: str) -> None:
        with self._dbmgr.transaction():
            self._dbmgr.insert("simulation_runs", {
                "run_id": run_id, "project_version": project_version,
                "config_hash": config_hash(config), "status": "queued",
            })
            self._dbmgr.insert("configurations", {
                "run_id": run_id,
                **dict(zip((p.replace('.', '_') for p in DSQL.CONFIGURATION_PATHS),
                           configuration_values(config))),
            })

    def mark_started(self, run_id: str) -> None:
        self._dbmgr.update("simulation_runs", {
            "status": "running", "started_at": SqlValue.CURRENT_TIMESTAMP,
        }, where={"run_id": run_id})

    def set_status(self, run_id: str, status: str) -> None:
        self._dbmgr.update("simulation_runs", {"status": status}, where={"run_id": run_id})

    def record_episode(self, run_id: str, result: "EpisodeResult",
                       episode_count: int, high_score: int) -> None:
        with self._dbmgr.transaction():
            self._dbmgr.insert("simulation_episodes", {
                "run_id": run_id, "episode": result.episode, "score": result.score,
                "steps": result.steps, "epsilon": result.epsilon, "loss": result.loss,
            })
            self._dbmgr.update("simulation_runs", {
                "episode_count": episode_count, "high_score": high_score,
            }, where={"run_id": run_id})

    def finish_run(self, run_id: str, status: str, episode_count: int, high_score: int,
                   error_message: str | None = None,
                   high_score_snapshot: dict[str, Any] | None = None) -> None:
        self._dbmgr.update("simulation_runs", {
            "status": status, "episode_count": episode_count, "high_score": high_score,
            "high_score_snapshot": json.dumps(high_score_snapshot, separators=(",", ":"), allow_nan=False)
                if high_score_snapshot is not None else None,
            "completed_at": SqlValue.CURRENT_TIMESTAMP, "error_message": error_message,
        }, where={"run_id": run_id})

    def get_high_score_snapshot(self, run_id: str) -> dict[str, Any] | None:
        row = self._dbmgr.select("simulation_runs", ("run_id", "high_score_snapshot"),
                                 where={"run_id": run_id}, one=True)
        if row is not None and row["high_score_snapshot"] is not None:
            row["high_score_snapshot"] = json.loads(row["high_score_snapshot"])
        return row

    def get_configuration(self, run_id: str) -> dict[str, Any] | None:
        """Read persisted configuration without changing simulation state."""
        with self._dbmgr.transaction(read_only=True):
            return self._dbmgr.select("configurations",
                tuple(p.replace('.', '_') for p in DSQL.CONFIGURATION_PATHS),
                where={"run_id": run_id}, one=True)

    def measure_and_delete_benchmark(self, run_id: str) -> tuple[int, float]:
        """Measure and delete one completed run atomically; return steps and seconds."""
        with self._dbmgr.transaction():
            run = self._dbmgr.select(
                "simulation_runs", ("status", "started_at", "completed_at"),
                where={"run_id": run_id}, one=True, for_update=True,
            )
            if not run or run["status"] != "completed":
                raise RuntimeError("Benchmark has no committed completed result")
            started, completed = run["started_at"], run["completed_at"]
            if started is None or completed is None:
                raise RuntimeError("Benchmark has no positive elapsed time")
            seconds = (completed - started).total_seconds()
            if seconds <= 0:
                raise RuntimeError("Benchmark has no positive elapsed time")
            steps = int(self._dbmgr.sum(
                "simulation_episodes", "steps", where={"run_id": run_id},
            ))
            # Configurations and episode results cascade from this parent row.
            self._dbmgr.delete("simulation_runs", where={"run_id": run_id})
        return steps, seconds

    def close(self) -> None:
        self._dbmgr.close()
