"""Stateful deterministic Snake environment."""

from __future__ import annotations

import random

from snake_lab.game.GameRules import GameRules
from snake_lab.game.GameState import GameState
from constants.DGame import Action
from snake_lab.game.Direction import Direction
from snake_lab.game.Position import Position
from snake_lab.game.RewardConfig import RewardConfig
from snake_lab.game.StepResult import StepResult
from snake_lab.game.GameHelper import random_free_position


class SnakeGame:
    """Stateful deterministic environment used by one simulation."""

    def __init__(
        self,
        *,
        seed: int,
        grid_size: tuple[int, int],
        initial_snake_length: int,
        max_moves_multiplier: int,
        rewards: RewardConfig,
        episode_id: int = 1,
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
        if type(episode_id) is not int or episode_id <= 0:
            raise ValueError("episode_id must be a positive integer")

        self.seed = seed
        self.grid_size = grid_size
        self.initial_snake_length = initial_snake_length
        self.max_moves_multiplier = max_moves_multiplier
        if not isinstance(rewards, RewardConfig):
            raise TypeError("rewards must be a RewardConfig")

        self.rewards = rewards
        self._rng = random.Random(seed)
        self._episode_id = episode_id - 1
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
        food = random_free_position(self._rng, self.grid_size, occupied)
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
