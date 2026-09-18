"""Immutable Snake game state and neural-network observation."""

from __future__ import annotations

from dataclasses import dataclass

from constants.DGame import DGameDef
from snake_lab.game.Direction import Direction
from snake_lab.game.Position import Position


@dataclass(frozen=True, slots=True)
class GameState:
    """Immutable snapshot of one Snake episode."""

    snake_head: Position
    snake_body: tuple[Position, ...]
    direction: Direction
    food_position: Position | None
    score: int
    move_count: int
    grid_size: tuple[int, int]
    seed: int
    episode_id: int

    @property
    def snake_length(self) -> int:
        return len(self.snake_body) + 1

    def contains(self, position: Position) -> bool:
        """Return whether a position is within the board."""
        width, height = self.grid_size
        return 0 <= position.x < width and 0 <= position.y < height

    def observation(self) -> tuple[float, ...]:
        """Return the fixed-size egocentric neural-network observation."""
        radius = DGameDef.OBSERVATION_RADIUS
        forward = self.direction
        right = Direction(-forward.dy, forward.dx)
        body = set(self.snake_body)
        values: list[float] = []

        for local_y in range(-radius, radius + 1):
            for local_x in range(-radius, radius + 1):
                if local_x == 0 and local_y == 0:
                    values.append(0.0)
                    continue

                position = Position(
                    self.snake_head.x
                    + local_x * right.dx
                    - local_y * forward.dx,
                    self.snake_head.y
                    + local_x * right.dy
                    - local_y * forward.dy,
                )
                if not self.contains(position):
                    values.append(-0.5)
                elif position in body:
                    values.append(0.5)
                elif position == self.food_position:
                    values.append(1.0)
                else:
                    values.append(0.0)

        if self.food_position is None:
            values.extend((0.0, 0.0))
        else:
            relative_x = self.food_position.x - self.snake_head.x
            relative_y = self.food_position.y - self.snake_head.y
            local_x = relative_x * right.dx + relative_y * right.dy
            local_y = -(
                relative_x * forward.dx + relative_y * forward.dy
            )
            values.extend((_sign(local_x), _sign(local_y)))

        if len(values) != DGameDef.OBSERVATION_SIZE:
            raise RuntimeError(
                "game observation size does not match its definition"
            )
        return tuple(values)


def _sign(value: int) -> float:
    if value < 0:
        return -1.0
    if value > 0:
        return 1.0
    return 0.0
