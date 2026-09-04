"""Typed, transport-neutral SnakeLab telemetry messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snake_lab.game import GameState, Outcome, StepResult
from snake_lab.protocol import PROTOCOL_VERSION, ProtocolError


TOPIC_PREFIX = "snake_lab"
TOPIC_RUN = f"{TOPIC_PREFIX}.run"
TOPIC_FRAME = f"{TOPIC_PREFIX}.frame"
TOPIC_EPISODE = f"{TOPIC_PREFIX}.episode"
TELEMETRY_TOPICS = (TOPIC_RUN, TOPIC_FRAME, TOPIC_EPISODE)


def _coordinate(value: Any, name: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(element) is not int for element in value)
    ):
        raise ProtocolError(
            "invalid_telemetry", f"{name} must contain two integers"
        )
    return value[0], value[1]


@dataclass(frozen=True, slots=True)
class BoardSnapshot:
    """A complete immutable board frame suitable for rendering."""

    width: int
    height: int
    snake_head: tuple[int, int]
    snake_body: tuple[tuple[int, int], ...]
    food: tuple[int, int] | None
    direction: tuple[int, int]
    score: int

    @classmethod
    def from_game_state(cls, state: GameState) -> "BoardSnapshot":
        return cls(
            width=state.grid_size[0],
            height=state.grid_size[1],
            snake_head=(state.snake_head.x, state.snake_head.y),
            snake_body=tuple(
                (position.x, position.y) for position in state.snake_body
            ),
            food=(
                (state.food_position.x, state.food_position.y)
                if state.food_position is not None
                else None
            ),
            direction=(state.direction.dx, state.direction.dy),
            score=state.score,
        )

    @classmethod
    def from_dict(cls, data: Any) -> "BoardSnapshot":
        if not isinstance(data, dict):
            raise ProtocolError(
                "invalid_telemetry", "board must be an object"
            )
        expected = {
            "grid_size",
            "snake_head",
            "snake_body",
            "food",
            "direction",
            "score",
        }
        if set(data) != expected:
            raise ProtocolError(
                "invalid_telemetry", "board fields do not match the protocol"
            )

        width, height = _coordinate(data["grid_size"], "grid_size")
        if width <= 0 or height <= 0:
            raise ProtocolError(
                "invalid_telemetry", "grid dimensions must be positive"
            )
        body_data = data["snake_body"]
        if not isinstance(body_data, list):
            raise ProtocolError(
                "invalid_telemetry", "snake_body must be an array"
            )
        body = tuple(
            _coordinate(position, "snake_body position")
            for position in body_data
        )
        food_data = data["food"]
        food = (
            None
            if food_data is None
            else _coordinate(food_data, "food")
        )
        score = data["score"]
        if type(score) is not int or score < 0:
            raise ProtocolError(
                "invalid_telemetry", "score must be a non-negative integer"
            )

        return cls(
            width=width,
            height=height,
            snake_head=_coordinate(data["snake_head"], "snake_head"),
            snake_body=body,
            food=food,
            direction=_coordinate(data["direction"], "direction"),
            score=score,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid_size": [self.width, self.height],
            "snake_head": list(self.snake_head),
            "snake_body": [list(position) for position in self.snake_body],
            "food": list(self.food) if self.food is not None else None,
            "direction": list(self.direction),
            "score": self.score,
        }


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


@dataclass(frozen=True, slots=True)
class TelemetryEnvelope:
    """Common JSON envelope carried after the ZeroMQ topic frame."""

    sequence: int
    run_id: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "TelemetryEnvelope":
        if not isinstance(data, dict):
            raise ProtocolError(
                "invalid_telemetry", "telemetry envelope must be an object"
            )
        expected = {"protocol_version", "sequence", "run_id", "payload"}
        if set(data) != expected:
            raise ProtocolError(
                "invalid_telemetry",
                "telemetry envelope fields do not match the protocol",
            )
        if data["protocol_version"] != PROTOCOL_VERSION:
            raise ProtocolError(
                "unsupported_protocol", "Unsupported telemetry protocol"
            )
        if type(data["sequence"]) is not int or data["sequence"] < 0:
            raise ProtocolError(
                "invalid_telemetry", "sequence must be a non-negative integer"
            )
        if not isinstance(data["run_id"], str) or not data["run_id"]:
            raise ProtocolError(
                "invalid_telemetry", "run_id must be a non-empty string"
            )
        if not isinstance(data["payload"], dict):
            raise ProtocolError(
                "invalid_telemetry", "payload must be an object"
            )
        return cls(data["sequence"], data["run_id"], data["payload"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "sequence": self.sequence,
            "run_id": self.run_id,
            "payload": self.payload,
        }
