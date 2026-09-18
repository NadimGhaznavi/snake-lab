"""State and runtime controls for a queued simulation."""

from dataclasses import dataclass, field
from typing import Any

from snake_lab.server.SimulationControl import SimulationControl
from snake_lab.server.Simulator import EpisodeResult


@dataclass(slots=True)
class SimulationRun:
    run_id: str
    config: dict[str, Any]
    state: str = "queued"
    completed_epochs: int = 0
    total_steps: int = 0
    high_score: int = 0
    high_score_snapshot: dict[str, Any] | None = None
    total_reward: float = 0.0
    epsilon_injections: int = 0
    last_loss: float | None = None
    last_episode: EpisodeResult | None = None
    error: str | None = None
    control: SimulationControl = field(default_factory=SimulationControl)

