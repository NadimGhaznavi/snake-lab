import random
import unittest
from dataclasses import replace

from snakelab.constants.DGame import DGameDef
from snakelab.constants.DNNet import DNetDef
from snakelab.game.GameRules import GameRules
from snakelab.game.GameState import GameState
from snakelab.constants.DGame import Action
from snakelab.game.Direction import Direction
from snakelab.constants.DGame import Outcome
from snakelab.game.Position import Position
from snakelab.game.RewardConfig import RewardConfig

from snakelab.game.SnakeGame import SnakeGame


TEST_REWARDS = RewardConfig(
    food=10.0,
    wall=-10.0,
    snake=-10.0,
    max_moves=-10.0,
    empty=0.0,
    closer_to_food=0.1,
    further_from_food=-0.1,
)


def make_game(seed: int = 7, **overrides) -> SnakeGame:
    values = {
        "grid_size": (20, 20),
        "initial_snake_length": 3,
        "max_moves_multiplier": 100,
        "rewards": TEST_REWARDS,
    }
    values.update(overrides)
    return SnakeGame(seed=seed, **values)


def make_state(
    *,
    head: Position = Position(2, 2),
    body: tuple[Position, ...] = (Position(1, 2), Position(0, 2)),
    direction: Direction = Direction(1, 0),
    food: Position | None = Position(4, 2),
    grid_size: tuple[int, int] = (5, 5),
    move_count: int = 0,
    max_moves_multiplier: int = 100,
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
        max_moves_multiplier=max_moves_multiplier,
    )


def step(state: GameState, action: Action | int):
    return GameRules.step(
        state,
        action,
        rng=random.Random(7),
        rewards=TEST_REWARDS,
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
        self.assertEqual(result.observation[10:16], (0.0,) * 6)

    def test_maximum_move_budget_is_terminal(self) -> None:
        state = make_state(move_count=300)
        result = GameRules.step(
            state,
            Action.STRAIGHT,
            rng=random.Random(7),
            rewards=TEST_REWARDS,
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

    def test_heading_and_food_use_fixed_board_axes(self) -> None:
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

        self.assertEqual(facing_right.observation()[6:10], (0., 1., 0., 0.))
        self.assertEqual(facing_down.observation()[6:10], (0., 0., 0., 1.))
        self.assertEqual(facing_right.observation()[10:16], (0., 1., 0., 0., 0., 1.))
        self.assertEqual(facing_down.observation()[10:16], (0., 0., 0., 1., 1., 0.))

    def test_exact_feature_order(self) -> None:
        self.assertEqual(make_state().observation(), (
            0., 0., 0.,  # body danger: left, straight, right
            0., 0., 0.,  # wall danger: left, straight, right
            0., 1., 0., 0.,  # heading: left, right, up, down
            0., 1., 0., 0., 0., 1.,  # food directions, same X, same Y
            0., 0., 0., 0., 0., 1., 1.,  # length 3, big-endian
            1.,  # remaining move budget
        ))

    def test_separate_body_and_wall_danger(self) -> None:
        state = make_state(
            head=Position(0, 0),
            body=(Position(0, 1), Position(1, 1)),
            direction=Direction(1, 0),
            food=Position(1, 0),
            grid_size=(4, 4),
        )
        self.assertEqual(state.observation()[:6], (0., 0., 1., 1., 0., 0.))

    def test_danger_matches_actual_moves_for_every_heading(self) -> None:
        for direction in (Direction.left(), Direction.right(), Direction.up(), Direction.down()):
            for head in (Position(0, 0), Position(2, 2), Position(4, 4)):
                state = make_state(
                    head=head, body=(Position(2, 1), Position(1, 1), Position(1, 2)),
                    direction=direction, food=Position(3, 3),
                )
                observation = state.observation()
                for action in Action:
                    with self.subTest(direction=direction, head=head, action=action):
                        result = step(state, action)
                        self.assertEqual(observation[action], float(result.outcome is Outcome.SNAKE))
                        self.assertEqual(observation[3 + action], float(result.outcome is Outcome.WALL))

    def test_vacating_tail_is_not_marked_as_danger(self) -> None:
        state = make_state(
            body=(Position(2, 1), Position(1, 1), Position(1, 2)),
            direction=Direction.down(), food=Position(4, 4),
        )
        self.assertEqual(state.observation()[Action.RIGHT], 0.)
        self.assertFalse(step(state, Action.RIGHT).is_collision)

    def test_length_saturates_instead_of_wrapping(self) -> None:
        for length in (1, 3, 127, 128, 400):
            state = make_state(body=tuple(Position(0, index) for index in range(length - 1)))
            expected = tuple(float(bit) for bit in f'{min(length, 127):07b}')
            self.assertEqual(state.observation()[16:23], expected)

    def test_move_budget_distinguishes_otherwise_identical_observations(self):
        fresh = make_state(max_moves_multiplier=10)
        halfway = replace(fresh, move_count=15)
        expired = replace(fresh, move_count=30)
        self.assertEqual(fresh.observation()[:-1], expired.observation()[:-1])
        self.assertEqual(fresh.observation()[-1], 1.)
        self.assertEqual(halfway.observation()[-1], .5)
        self.assertEqual(expired.observation()[-1], 0.)
        self.assertEqual(replace(expired, move_count=31).observation()[-1], 0.)
        result = GameRules.step(
            expired, Action.STRAIGHT, rng=random.Random(7), rewards=TEST_REWARDS,
        )
        self.assertEqual(result.outcome, Outcome.MAX_MOVES)
        self.assertEqual(result.observation[-1], 0.)

    def test_growth_updates_budget_using_the_actual_snake_length(self):
        state = make_state(food=Position(3, 2), move_count=150)
        result = step(state, Action.STRAIGHT)
        self.assertEqual(state.observation()[-1], .5)
        self.assertAlmostEqual(result.observation[-1], 1 - 151 / 400)

    def test_reset_restores_the_configured_budget(self):
        game = make_game(max_moves_multiplier=7)
        self.assertEqual(game.state.move_limit, 21)
        self.assertAlmostEqual(game.step(Action.STRAIGHT).observation[-1], 20 / 21)
        self.assertEqual(game.reset()[-1], 1.)
        self.assertEqual(game.state.move_limit, 21)

    def test_no_food_has_no_food_features(self) -> None:
        self.assertEqual(make_state(food=None).observation()[10:16], (0.,) * 6)


class SnakeGameTests(unittest.TestCase):
    def test_same_seed_and_actions_are_reproducible(self) -> None:
        first = make_game(seed=19)
        second = make_game(seed=19)

        self.assertEqual(first.state, second.state)
        for action in (Action.LEFT, Action.RIGHT, Action.STRAIGHT):
            self.assertEqual(first.step(action), second.step(action))

    def test_reset_starts_a_new_episode(self) -> None:
        game = make_game(seed=7)
        first_episode = game.state.episode_id
        observation = game.reset()

        self.assertEqual(game.state.episode_id, first_episode + 1)
        self.assertEqual(observation, game.observe())
        self.assertFalse(game.done)

    def test_initial_snake_is_in_bounds_for_custom_length(self) -> None:
        game = make_game(
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
        game = make_game(
            seed=7,
            grid_size=(4, 1),
            initial_snake_length=3,
        )
        game.step(Action.STRAIGHT)
        self.assertTrue(game.done)

        with self.assertRaises(RuntimeError):
            game.step(Action.STRAIGHT)

    def test_invalid_actions_are_rejected(self) -> None:
        game = make_game(seed=7)
        for action in (-1, 3, True, "1"):
            with self.subTest(action=action):
                with self.assertRaises((TypeError, ValueError)):
                    game.step(action)


if __name__ == "__main__":
    unittest.main()
