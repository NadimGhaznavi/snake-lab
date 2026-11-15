"""Immutable Snake game state and neural-network observation."""

from __future__ import annotations

from dataclasses import dataclass

from snakelab.constants.DGame import DGameDef, Outcome
from snakelab.game.Direction import Direction
from snakelab.game.Position import Position


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
    max_moves_multiplier: int

    @property
    def snake_length(self) -> int:
        return len(self.snake_body) + 1

    @property
    def move_limit(self) -> int:
        return self.max_moves_multiplier * self.snake_length

    def contains(self, position: Position) -> bool:
        """Return whether a position is within the board."""
        width, height = self.grid_size
        return 0 <= position.x < width and 0 <= position.y < height

    def collision_at(self, position: Position) -> Outcome | None:
        """Classify a destination, allowing a non-growing move into the tail."""
        if not self.contains(position):
            return Outcome.WALL
        if position in self.snake_body and (
            position != self.snake_body[-1] or position == self.food_position
        ):
            return Outcome.SNAKE
        return None

    def observation(self) -> tuple[float, ...]:
        """Return Hydra's 23 features followed by the remaining move budget.

        Danger is ordered left/straight/right, separately for body and wall.
        Heading and food use fixed board axes, ordered left/right/up/down.
        Length is big-endian and saturates at 127 instead of wrapping.
        The final value is the unused fraction of the current move limit.
        """
        directions = (
            self.direction.turn_left(), self.direction, self.direction.turn_right(),
        )
        collisions = tuple(
            self.collision_at(Position(
                self.snake_head.x + direction.dx,
                self.snake_head.y + direction.dy,
            ))
            for direction in directions
        )
        heading = (self.direction.dx, self.direction.dy)
        food = self.food_position
        food_features = (False,) * 6 if food is None else (
            food.x < self.snake_head.x,
            food.x > self.snake_head.x,
            food.y < self.snake_head.y,
            food.y > self.snake_head.y,
            food.x == self.snake_head.x,
            food.y == self.snake_head.y,
        )
        bits = DGameDef.STATE_LENGTH_BITS
        length = min(self.snake_length, (1 << bits) - 1)
        return (
            *(float(value is Outcome.SNAKE) for value in collisions),
            *(float(value is Outcome.WALL) for value in collisions),
            *(float(heading == vector) for vector in (
                (-1, 0), (1, 0), (0, -1), (0, 1),
            )),
            *map(float, food_features),
            *(float((length >> bit) & 1) for bit in range(bits - 1, -1, -1)),
            max(0.0, 1.0 - self.move_count / self.move_limit),
        )
