import random
import unittest

from constants.DGame import DGameDef
from constants.DNNet import DNetDef
from snake_lab.game import (
    Action,
    Direction,
    GameRules,
    GameState,
    Outcome,
    Position,
    RewardConfig,
    SnakeGame,
)


def make_state(
    *,
    head: Position = Position(2, 2),
    body: tuple[Position, ...] = (Position(1, 2), Position(0, 2)),
    direction: Direction = Direction(1, 0),
    food: Position | None = Position(4, 2),
    grid_size: tuple[int, int] = (5, 5),
    move_count: int = 0,
) -> GameState:
    return GameState(
        snake_head=head,
        snake_body=body,
        direction=direction,
        food_position=food,
        score=0,
        move_count=move_count,
        grid_size=grid_size,
        seed=7,
        episode_id=1,
    )


def step(state: GameState, action: Action | int):
    return GameRules.step(
        state,
        action,
        rng=random.Random(7),
        rewards=RewardConfig(),
        max_moves_multiplier=100,
    )


class GameRulesTests(unittest.TestCase):
    def test_relative_actions_turn_from_current_direction(self) -> None:
        left = step(make_state(), Action.LEFT)
        straight = step(make_state(), Action.STRAIGHT)
        right = step(make_state(), Action.RIGHT)

        self.assertEqual(left.new_state.direction, Direction(0, -1))
        self.assertEqual(straight.new_state.direction, Direction(1, 0))
        self.assertEqual(right.new_state.direction, Direction(0, 1))

    def test_empty_move_shifts_body_and_shapes_reward(self) -> None:
        result = step(make_state(), Action.STRAIGHT)

        self.assertEqual(result.new_state.snake_head, Position(3, 2))
        self.assertEqual(
            result.new_state.snake_body,
            (Position(2, 2), Position(1, 2)),
        )
        self.assertEqual(result.reward, 0.1)
        self.assertEqual(result.outcome, Outcome.EMPTY)
        self.assertFalse(result.done)

    def test_food_grows_snake_and_spawns_unoccupied_food(self) -> None:
        state = make_state(food=Position(3, 2))
        result = step(state, Action.STRAIGHT)

        self.assertEqual(result.new_state.snake_head, Position(3, 2))
        self.assertEqual(
            result.new_state.snake_body,
            (Position(2, 2), Position(1, 2), Position(0, 2)),
        )
        self.assertNotIn(
            result.new_state.food_position,
            {result.new_state.snake_head, *result.new_state.snake_body},
        )
        self.assertEqual(result.new_state.score, 1)
        self.assertEqual(result.reward, 10.0)
        self.assertEqual(result.outcome, Outcome.FOOD)

    def test_wall_collision_is_terminal(self) -> None:
        state = make_state(
            head=Position(4, 2),
            body=(Position(3, 2), Position(2, 2)),
        )
        result = step(state, Action.STRAIGHT)

        self.assertTrue(result.done)
        self.assertTrue(result.is_collision)
        self.assertEqual(result.outcome, Outcome.WALL)
        self.assertEqual(result.reward, -10.0)
        self.assertEqual(result.new_state.snake_head, state.snake_head)

    def test_retained_body_collision_is_terminal(self) -> None:
        state = make_state(
            head=Position(2, 2),
            body=(Position(2, 1), Position(1, 1), Position(1, 2)),
            direction=Direction(1, 0),
            food=Position(4, 4),
        )
        result = step(state, Action.LEFT)

        self.assertTrue(result.done)
        self.assertEqual(result.outcome, Outcome.SNAKE)
        self.assertTrue(GameRules.would_collide(state, Action.LEFT))

    def test_moving_into_vacating_tail_is_legal(self) -> None:
        state = make_state(
            head=Position(2, 2),
            body=(Position(2, 1), Position(1, 1), Position(1, 2)),
            direction=Direction(0, 1),
            food=Position(4, 4),
        )

        self.assertFalse(GameRules.would_collide(state, Action.RIGHT))
        result = step(state, Action.RIGHT)
        self.assertFalse(result.done)
        self.assertEqual(result.new_state.snake_head, Position(1, 2))

    def test_eating_last_free_cell_completes_board(self) -> None:
        state = make_state(
            head=Position(0, 0),
            body=(Position(0, 1), Position(1, 1)),
            direction=Direction(1, 0),
            food=Position(1, 0),
            grid_size=(2, 2),
        )
        result = step(state, Action.STRAIGHT)

        self.assertTrue(result.done)
        self.assertEqual(result.outcome, Outcome.BOARD_FILLED)
        self.assertIsNone(result.new_state.food_position)
        self.assertEqual(result.observation[-2:], (0.0, 0.0))

    def test_maximum_move_budget_is_terminal(self) -> None:
        state = make_state(move_count=300)
        result = GameRules.step(
            state,
            Action.STRAIGHT,
            rng=random.Random(7),
            rewards=RewardConfig(),
            max_moves_multiplier=100,
        )

        self.assertTrue(result.done)
        self.assertEqual(result.outcome, Outcome.MAX_MOVES)
        self.assertEqual(result.new_state.move_count, 301)
        self.assertEqual(result.new_state.snake_head, state.snake_head)


class ObservationTests(unittest.TestCase):
    def test_observation_matches_model_input_size(self) -> None:
        observation = make_state().observation()
        self.assertEqual(len(observation), DGameDef.OBSERVATION_SIZE)
        self.assertEqual(len(observation), DNetDef.INPUT_SIZE)

    def test_observation_is_egocentric(self) -> None:
        facing_right = make_state(
            head=Position(3, 3),
            body=(Position(2, 3),),
            direction=Direction(1, 0),
            food=Position(5, 3),
            grid_size=(7, 7),
        )
        facing_down = make_state(
            head=Position(3, 3),
            body=(Position(3, 2),),
            direction=Direction(0, 1),
            food=Position(3, 5),
            grid_size=(7, 7),
        )

        self.assertEqual(
            facing_right.observation(),
            facing_down.observation(),
        )

    def test_observation_marks_wall_body_and_food(self) -> None:
        state = make_state(
            head=Position(1, 1),
            body=(Position(0, 1),),
            direction=Direction(1, 0),
            food=Position(2, 1),
            grid_size=(4, 4),
        )
        observation = state.observation()
        width = DGameDef.OBSERVATION_RADIUS * 2 + 1
        center = DGameDef.OBSERVATION_RADIUS

        def value(local_x: int, local_y: int) -> float:
            return observation[(center + local_y) * width + center + local_x]

        self.assertEqual(value(0, -1), 1.0)
        self.assertEqual(value(0, 1), 0.5)
        self.assertEqual(value(-2, 0), -0.5)
        self.assertEqual(observation[-2:], (0.0, -1.0))


class SnakeGameTests(unittest.TestCase):
    def test_same_seed_and_actions_are_reproducible(self) -> None:
        first = SnakeGame(seed=19)
        second = SnakeGame(seed=19)

        self.assertEqual(first.state, second.state)
        for action in (Action.LEFT, Action.RIGHT, Action.STRAIGHT):
            self.assertEqual(first.step(action), second.step(action))

    def test_reset_starts_a_new_episode(self) -> None:
        game = SnakeGame(seed=7)
        first_episode = game.state.episode_id
        observation = game.reset()

        self.assertEqual(game.state.episode_id, first_episode + 1)
        self.assertEqual(observation, game.observe())
        self.assertFalse(game.done)

    def test_initial_snake_is_in_bounds_for_custom_length(self) -> None:
        game = SnakeGame(
            seed=7,
            grid_size=(4, 2),
            initial_snake_length=4,
        )

        positions = {game.state.snake_head, *game.state.snake_body}
        self.assertEqual(len(positions), 4)
        self.assertTrue(
            all(game.state.contains(position) for position in positions)
        )

    def test_completed_episode_must_be_reset_before_stepping(self) -> None:
        game = SnakeGame(
            seed=7,
            grid_size=(4, 1),
            initial_snake_length=3,
        )
        game.step(Action.STRAIGHT)
        self.assertTrue(game.done)

        with self.assertRaises(RuntimeError):
            game.step(Action.STRAIGHT)

    def test_invalid_actions_are_rejected(self) -> None:
        game = SnakeGame(seed=7)
        for action in (-1, 3, True, "1"):
            with self.subTest(action=action):
                with self.assertRaises((TypeError, ValueError)):
                    game.step(action)


if __name__ == "__main__":
    unittest.main()
