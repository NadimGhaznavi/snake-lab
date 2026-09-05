import random
import unittest
from unittest.mock import patch

import torch

from snake_lab.game import (
    Direction, GameRules, GameState, Outcome, Position, RewardConfig,
)
from snake_lab.tensor_game import TensorSnakeGame


REWARDS = RewardConfig(
    food=10, wall=-10, snake=-11, max_moves=-12, empty=0,
    closer_to_food=0.1, further_from_food=-0.1,
)


class TensorGameTests(unittest.TestCase):
    device = torch.device("cpu")

    def make_game(self, width=6, height=5, length=3, limit=100, seed=7):
        return TensorSnakeGame(
            seed=seed, episode_id=1, grid_size=(width, height),
            initial_snake_length=length, max_moves_multiplier=limit,
            rewards=REWARDS, device=self.device,
        )

    def load_state(self, game, state):
        game.ages.zero_()
        coordinates = (state.snake_head, *state.snake_body)
        for index, point in enumerate(coordinates):
            game.ages[0, point.x * game.height + point.y] = len(coordinates) - index
        game.head = torch.tensor([[state.snake_head.x, state.snake_head.y]], device=self.device)
        game.direction = torch.tensor([[state.direction.dx, state.direction.dy]], device=self.device)
        game.food = torch.tensor([[state.food_position.x, state.food_position.y]], device=self.device)
        game.length.fill_(len(coordinates))
        game.moves.fill_(state.move_count)
        game.score.fill_(state.score)

    def compare_step(self, game, action):
        before = game.export_step().new_state
        observation = game.step(torch.tensor([action], device=self.device))
        actual = game.export_step()
        # Food generators differ; supply the tensor-selected food to the pure
        # reference rules while independently checking it is a legal free cell.
        with patch("snake_lab.game._random_free_position", return_value=actual.new_state.food_position):
            expected = GameRules.step(
                before, action, rng=random.Random(7), rewards=REWARDS,
                max_moves_multiplier=game.max_moves_multiplier,
            )
        self.assertEqual(actual.new_state, expected.new_state)
        self.assertEqual(actual.outcome, expected.outcome)
        self.assertEqual(actual.done, expected.done)
        self.assertAlmostEqual(actual.reward, expected.reward, places=5)
        torch.testing.assert_close(
            observation, torch.tensor([expected.observation], device=self.device),
        )
        if actual.new_state.food_position is not None:
            self.assertTrue(actual.new_state.contains(actual.new_state.food_position))
            self.assertNotIn(actual.new_state.food_position, (actual.new_state.snake_head, *actual.new_state.snake_body))
        return actual

    def test_scripted_rules_and_observations(self):
        rng = random.Random(19)
        for seed in range(20):
            game = self.make_game(seed=seed)
            self.assertEqual(game.observe().shape, (1, 51))
            for _ in range(100):
                if self.compare_step(game, rng.randrange(3)).done:
                    break

    def test_food_growth_board_completion_and_limit_precedence(self):
        game = self.make_game(width=4, height=1, length=3)
        result = self.compare_step(game, 1)
        self.assertEqual(result.outcome, Outcome.BOARD_FILLED)
        self.assertEqual(result.new_state.score, 1)
        self.assertIsNone(result.new_state.food_position)
        game = self.make_game(width=4, height=1, length=3, limit=1)
        game.moves.fill_(3)
        self.assertEqual(self.compare_step(game, 0).outcome, Outcome.MAX_MOVES)
        game = self.make_game()
        game.food = game.head + game.direction
        result = self.compare_step(game, 1)
        self.assertEqual(result.outcome, Outcome.FOOD)
        self.assertEqual(result.new_state.snake_length, 4)

    def test_vacating_tail_is_legal_but_retained_body_collides(self):
        state = GameState(
            snake_head=Position(2, 2),
            snake_body=(Position(2, 3), Position(1, 3), Position(1, 2)),
            direction=Direction.up(), food_position=Position(5, 4),
            score=1, move_count=4, grid_size=(6, 5), seed=7, episode_id=1,
        )
        game = self.make_game()
        self.load_state(game, state)
        self.assertFalse(self.compare_step(game, 0).done)
        game = self.make_game()
        self.load_state(game, state)
        game.direction = torch.tensor([[-1, 0]], device=self.device)
        self.assertEqual(self.compare_step(game, 0).outcome, Outcome.SNAKE)

    def test_device_seed_reproducibility(self):
        first, second = self.make_game(), self.make_game()
        for action in (1, 2, 1, 0, 1):
            tensor = torch.tensor([action], device=self.device)
            torch.testing.assert_close(first.step(tensor), second.step(tensor))
            torch.testing.assert_close(first.food, second.food)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA device required")
class CudaTensorGameTests(TensorGameTests):
    device = torch.device("cuda")
