"""Immutable board snapshots for rendering and telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snake_lab.game.GameState import GameState


class BoardSnapshotError(ValueError):
    """A board snapshot cannot be decoded from the supplied data."""


def _coordinate(value: Any, name: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(element) is not int for element in value)
    ):
        raise BoardSnapshotError(
            f"{name} must contain two integers"
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
            raise BoardSnapshotError(
                "board must be an object"
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
            raise BoardSnapshotError(
                "board fields do not match the protocol"
            )

        width, height = _coordinate(data["grid_size"], "grid_size")
        if width <= 0 or height <= 0:
            raise BoardSnapshotError(
                "grid dimensions must be positive"
            )
        body_data = data["snake_body"]
        if not isinstance(body_data, list):
            raise BoardSnapshotError(
                "snake_body must be an array"
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
            raise BoardSnapshotError(
                "score must be a non-negative integer"
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
