"""Deterministic Snake game state, rules, and environment."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum

from constants.DGame import DGameDef


class Action(IntEnum):
    """Actions relative to the snake's current direction."""

    LEFT = 0
    STRAIGHT = 1
    RIGHT = 2


class Outcome(StrEnum):
    """Result category for one attempted move."""

    EMPTY = "empty"
    FOOD = "food"
    WALL = "wall"
    SNAKE = "snake"
    MAX_MOVES = "max_moves"
    BOARD_FILLED = "board_filled"


@dataclass(frozen=True, slots=True)
class Position:
    """One integer coordinate on the board."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class Direction:
    """One cardinal movement vector."""

    dx: int
    dy: int

    def __post_init__(self) -> None:
        if (self.dx, self.dy) not in {
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
        }:
            raise ValueError("direction must be a cardinal unit vector")

    @classmethod
    def left(cls) -> Direction:
        return cls(-1, 0)

    @classmethod
    def right(cls) -> Direction:
        return cls(1, 0)

    @classmethod
    def up(cls) -> Direction:
        return cls(0, -1)

    @classmethod
    def down(cls) -> Direction:
        return cls(0, 1)

    def turn_left(self) -> Direction:
        return Direction(self.dy, -self.dx)

    def turn_right(self) -> Direction:
        return Direction(-self.dy, self.dx)


@dataclass(frozen=True, slots=True)
class RewardConfig:
    """Rewards applied by the game rules."""

    food: float = DGameDef.FOOD_REWARD
    wall: float = DGameDef.WALL_REWARD
    snake: float = DGameDef.SNAKE_REWARD
    max_moves: float = DGameDef.MAX_MOVES_REWARD
    empty: float = DGameDef.EMPTY_REWARD
    closer_to_food: float = DGameDef.CLOSER_TO_FOOD_REWARD
    further_from_food: float = DGameDef.FURTHER_FROM_FOOD_REWARD

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} reward must be numeric")
            object.__setattr__(self, name, float(value))


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


def _sign(value: int) -> float:
    if value < 0:
        return -1.0
    if value > 0:
        return 1.0
    return 0.0


def _normalize_action(action: Action | int) -> Action:
    if isinstance(action, Action):
        return action
    if type(action) is not int:
        raise TypeError("action must be an Action or integer")
    try:
        return Action(action)
    except ValueError as error:
        raise ValueError(f"invalid action index: {action}") from error


def _next_direction(direction: Direction, action: Action) -> Direction:
    if action is Action.LEFT:
        return direction.turn_left()
    if action is Action.RIGHT:
        return direction.turn_right()
    return direction


def _random_free_position(
    rng: random.Random,
    grid_size: tuple[int, int],
    occupied: set[Position],
) -> Position | None:
    width, height = grid_size
    free = [
        Position(x, y)
        for x in range(width)
        for y in range(height)
        if Position(x, y) not in occupied
    ]
    return rng.choice(free) if free else None


class GameRules:
    """Pure Snake mechanics operating on immutable states."""

    @staticmethod
    def step(
        state: GameState,
        action: Action | int,
        *,
        rng: random.Random,
        rewards: RewardConfig,
        max_moves_multiplier: int,
    ) -> StepResult:
        """Apply an action deterministically for the supplied RNG state."""
        if type(max_moves_multiplier) is not int or max_moves_multiplier <= 0:
            raise ValueError("max_moves_multiplier must be a positive integer")
        if state.food_position is None:
            raise RuntimeError("cannot step a completed game state")

        normalized = _normalize_action(action)
        direction = _next_direction(state.direction, normalized)
        move_count = state.move_count + 1

        if move_count > max_moves_multiplier * state.snake_length:
            new_state = replace(state, move_count=move_count)
            return GameRules._result(
                new_state, rewards.max_moves, Outcome.MAX_MOVES, True
            )

        new_head = Position(
            state.snake_head.x + direction.dx,
            state.snake_head.y + direction.dy,
        )
        if not state.contains(new_head):
            new_state = replace(state, move_count=move_count)
            return GameRules._result(
                new_state, rewards.wall, Outcome.WALL, True
            )

        ate_food = new_head == state.food_position
        occupied_body = (
            state.snake_body if ate_food else state.snake_body[:-1]
        )
        if new_head in occupied_body:
            new_state = replace(state, move_count=move_count)
            return GameRules._result(
                new_state, rewards.snake, Outcome.SNAKE, True
            )

        if ate_food:
            body = (state.snake_head,) + state.snake_body
            food = _random_free_position(
                rng,
                state.grid_size,
                {new_head, *body},
            )
            new_state = replace(
                state,
                snake_head=new_head,
                snake_body=body,
                direction=direction,
                food_position=food,
                score=state.score + 1,
                move_count=move_count,
            )
            outcome = (
                Outcome.FOOD if food is not None else Outcome.BOARD_FILLED
            )
            return GameRules._result(
                new_state,
                rewards.food,
                outcome,
                food is None,
            )

        body = (state.snake_head,) + state.snake_body[:-1]
        new_state = replace(
            state,
            snake_head=new_head,
            snake_body=body,
            direction=direction,
            move_count=move_count,
        )
        old_distance = GameRules._food_distance(
            state.snake_head, state.food_position
        )
        new_distance = GameRules._food_distance(
            new_head, state.food_position
        )
        shaping = (
            rewards.closer_to_food
            if new_distance < old_distance
            else rewards.further_from_food
        )
        return GameRules._result(
            new_state,
            rewards.empty + shaping,
            Outcome.EMPTY,
            False,
        )

    @staticmethod
    def would_collide(state: GameState, action: Action | int) -> bool:
        """Return whether an action would hit a wall or retained body."""
        normalized = _normalize_action(action)
        direction = _next_direction(state.direction, normalized)
        new_head = Position(
            state.snake_head.x + direction.dx,
            state.snake_head.y + direction.dy,
        )
        if not state.contains(new_head):
            return True
        ate_food = new_head == state.food_position
        occupied_body = (
            state.snake_body if ate_food else state.snake_body[:-1]
        )
        return new_head in occupied_body

    @staticmethod
    def _food_distance(head: Position, food: Position) -> int:
        return abs(head.x - food.x) + abs(head.y - food.y)

    @staticmethod
    def _result(
        state: GameState,
        reward: float,
        outcome: Outcome,
        done: bool,
    ) -> StepResult:
        return StepResult(
            new_state=state,
            observation=state.observation(),
            reward=float(reward),
            outcome=outcome,
            done=done,
        )


class SnakeGame:
    """Stateful deterministic environment used by one simulation."""

    def __init__(
        self,
        *,
        seed: int,
        grid_size: tuple[int, int] = (
            DGameDef.BOARD_WIDTH,
            DGameDef.BOARD_HEIGHT,
        ),
        initial_snake_length: int = DGameDef.INITIAL_SNAKE_LENGTH,
        max_moves_multiplier: int = DGameDef.MAX_MOVES_MULTIPLIER,
        rewards: RewardConfig | None = None,
    ) -> None:
        if type(seed) is not int:
            raise TypeError("seed must be an integer")
        if (
            not isinstance(grid_size, tuple)
            or len(grid_size) != 2
            or any(type(value) is not int or value <= 0 for value in grid_size)
        ):
            raise ValueError("grid_size must contain two positive integers")
        if type(initial_snake_length) is not int or initial_snake_length <= 0:
            raise ValueError("initial_snake_length must be a positive integer")
        if initial_snake_length > grid_size[0]:
            raise ValueError(
                "initial snake must fit horizontally on the board"
            )
        if initial_snake_length >= grid_size[0] * grid_size[1]:
            raise ValueError(
                "board must have a free position for initial food"
            )
        if type(max_moves_multiplier) is not int or max_moves_multiplier <= 0:
            raise ValueError("max_moves_multiplier must be a positive integer")

        self.seed = seed
        self.grid_size = grid_size
        self.initial_snake_length = initial_snake_length
        self.max_moves_multiplier = max_moves_multiplier
        self.rewards = rewards or RewardConfig()
        self._rng = random.Random(seed)
        self._episode_id = 0
        self._done = False
        self._state = self._new_state()

    @property
    def state(self) -> GameState:
        return self._state

    @property
    def done(self) -> bool:
        return self._done

    def observe(self) -> tuple[float, ...]:
        return self._state.observation()

    def reset(self) -> tuple[float, ...]:
        """Start the next episode and return its initial observation."""
        self._state = self._new_state()
        self._done = False
        return self.observe()

    def step(self, action: Action | int) -> StepResult:
        """Apply one action to the current episode."""
        if self._done:
            raise RuntimeError("cannot step a completed episode; call reset()")
        result = GameRules.step(
            self._state,
            action,
            rng=self._rng,
            rewards=self.rewards,
            max_moves_multiplier=self.max_moves_multiplier,
        )
        self._state = result.new_state
        self._done = result.done
        return result

    def would_collide(self, action: Action | int) -> bool:
        return GameRules.would_collide(self._state, action)

    def _new_state(self) -> GameState:
        self._episode_id += 1
        width, height = self.grid_size
        head = Position(
            max(width // 2, self.initial_snake_length - 1),
            height // 2,
        )
        body = tuple(
            Position(head.x - offset, head.y)
            for offset in range(1, self.initial_snake_length)
        )
        occupied = {head, *body}
        food = _random_free_position(self._rng, self.grid_size, occupied)
        if food is None:
            raise RuntimeError("new game has no free position for food")
        return GameState(
            snake_head=head,
            snake_body=body,
            direction=Direction.right(),
            food_position=food,
            score=0,
            move_count=0,
            grid_size=self.grid_size,
            seed=self.seed,
            episode_id=self._episode_id,
        )
