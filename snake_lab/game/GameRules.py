"""Pure Snake mechanics operating on immutable states."""

from __future__ import annotations

import random
from dataclasses import replace

from constants.DGame import Action
from snake_lab.game.Direction import Direction
from constants.DGame import Outcome
from snake_lab.game.Position import Position
from snake_lab.game.RewardConfig import RewardConfig
from snake_lab.game.StepResult import StepResult
from snake_lab.game.GameHelper import random_free_position
from snake_lab.game.GameState import GameState


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
            food = random_free_position(
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
