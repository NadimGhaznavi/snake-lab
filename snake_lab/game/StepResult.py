"""State and reinforcement signal produced by one move."""

from __future__ import annotations

from dataclasses import dataclass

from constants.DGame import Outcome
from snake_lab.game.GameState import GameState


@dataclass(frozen=True, slots=True)
class StepResult:
    """State and reinforcement signal produced by one move."""

    new_state: GameState
    observation: tuple[float, ...]
    reward: float
    outcome: Outcome
    done: bool

    @property
    def is_collision(self) -> bool:
        return self.outcome in (Outcome.WALL, Outcome.SNAKE)
