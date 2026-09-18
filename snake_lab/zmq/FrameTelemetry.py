"""Telemetry for one game step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snake_lab.game.BoardSnapshot import BoardSnapshot
from snake_lab.game import Outcome, StepResult
from snake_lab.zmq.Protocol import ProtocolError


@dataclass(frozen=True, slots=True)
class FrameTelemetry:
    """One coherent post-move frame emitted by the simulation."""

    episode: int
    step: int
    action: int
    reward: float
    done: bool
    outcome: Outcome
    board: BoardSnapshot

    @classmethod
    def from_step(
        cls, *, episode: int, action: int, result: StepResult
    ) -> "FrameTelemetry":
        return cls(
            episode=episode,
            step=result.new_state.move_count,
            action=action,
            reward=result.reward,
            done=result.done,
            outcome=result.outcome,
            board=BoardSnapshot.from_game_state(result.new_state),
        )

    @classmethod
    def from_dict(cls, data: Any) -> "FrameTelemetry":
        if not isinstance(data, dict):
            raise ProtocolError(
                "invalid_telemetry", "frame payload must be an object"
            )
        expected = {
            "episode",
            "step",
            "action",
            "reward",
            "done",
            "outcome",
            "board",
        }
        if set(data) != expected:
            raise ProtocolError(
                "invalid_telemetry", "frame fields do not match the protocol"
            )
        for name in ("episode", "step", "action"):
            if type(data[name]) is not int or data[name] < 0:
                raise ProtocolError(
                    "invalid_telemetry",
                    f"{name} must be a non-negative integer",
                )
        reward = data["reward"]
        if isinstance(reward, bool) or not isinstance(reward, (int, float)):
            raise ProtocolError(
                "invalid_telemetry", "reward must be numeric"
            )
        if type(data["done"]) is not bool:
            raise ProtocolError(
                "invalid_telemetry", "done must be a boolean"
            )
        try:
            outcome = Outcome(data["outcome"])
        except (TypeError, ValueError) as error:
            raise ProtocolError(
                "invalid_telemetry", "outcome is not recognized"
            ) from error

        return cls(
            episode=data["episode"],
            step=data["step"],
            action=data["action"],
            reward=float(reward),
            done=data["done"],
            outcome=outcome,
            board=BoardSnapshot.from_dict(data["board"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode,
            "step": self.step,
            "action": self.action,
            "reward": self.reward,
            "done": self.done,
            "outcome": self.outcome.value,
            "board": self.board.to_dict(),
        }
