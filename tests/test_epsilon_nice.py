"""Hydra-style safe detours and their composition with ordinary exploration."""

from collections import deque
from random import Random
import unittest
from unittest.mock import Mock

import torch

from snakelab.constants.DGame import Action
from snakelab.game.Direction import Direction
from snakelab.game.GameRules import GameRules
from snakelab.game.Position import Position
from snakelab.nn.ActionPolicy import ActionPolicy
from snakelab.nn.EpsilonAlgo import EpsilonAlgo
from snakelab.nn.EpsilonNiceAlgo import EpsilonNiceAlgo
from tests.test_game import make_state
from tests.test_training import FakeLog


def make_nice(probability=1., steps=2, seed=7):
    return EpsilonNiceAlgo(rng=Random(seed), probability=probability, steps=steps, log=FakeLog())


class EpsilonNiceTests(unittest.TestCase):
    def test_gate_preserves_current_move_then_runs_exact_burst(self):
        nice, state = make_nice(), make_state()
        actions = [nice.select_action(Action.STRAIGHT, state, 0.) for _ in range(7)]
        self.assertEqual([action == Action.STRAIGHT for action in actions],
                         [True, False, False, True, False, False, True])
        self.assertEqual(nice.episode_injections, 4)
        self.assertEqual(nice.get_stats()['calls'], 7)

    def test_ordinary_epsilon_and_disabled_nice_preserve_suggestions(self):
        for probability, epsilon in ((0., 0.), (1., .5)):
            nice = make_nice(probability=probability)
            for _ in range(20):
                self.assertEqual(nice.select_action(1, make_state(), epsilon), 1)
            self.assertEqual(nice.get_stats()['calls'], 0)

    def test_override_avoids_fatal_suggestion(self):
        state = make_state(head=Position(4, 2))
        nice = make_nice()
        for _ in range(20):
            chosen = nice.override_action(Action.STRAIGHT, state)
            self.assertNotEqual(chosen, Action.STRAIGHT)
            self.assertFalse(GameRules.would_collide(state, chosen))
        self.assertEqual(nice.get_stats()['fatal_suggested'], 20)

    def test_safe_suggestion_is_also_changed_during_detour(self):
        state = make_state()
        self.assertNotEqual(make_nice().override_action(Action.STRAIGHT, state), Action.STRAIGHT)

    def test_no_safe_alternative_retains_even_a_fatal_suggestion(self):
        state = make_state(head=Position(0, 0), direction=Direction.up(),
                           body=(Position(1, 0), Position(1, 1)))
        nice = make_nice()
        self.assertEqual(nice.override_action(Action.STRAIGHT, state), Action.STRAIGHT)
        self.assertEqual(nice.get_stats()['no_safe_alternative'], 1)
        self.assertEqual(nice.episode_injections, 0)

    def test_vacating_tail_is_a_safe_alternative(self):
        state = make_state(head=Position(0, 1), direction=Direction.up(),
                           body=(Position(1, 1), Position(1, 0)), food=Position(3, 3))
        # Only straight is safe here; make the retained body the suggested turn.
        self.assertEqual(make_nice().override_action(Action.RIGHT, state), Action.STRAIGHT)
        tail_state = make_state(
            head=Position(0, 0), direction=Direction.up(),
            body=(Position(0, 1), Position(1, 1), Position(1, 0)),
        )
        self.assertEqual(make_nice().override_action(Action.STRAIGHT, tail_state), Action.RIGHT)

    def test_episode_reset_discards_remaining_detour(self):
        nice, state = make_nice(steps=10), make_state()
        nice.select_action(1, state, 0.)
        nice.select_action(1, state, 0.)
        nice.reset_episode()
        self.assertEqual(nice.episode_injections, 0)
        self.assertEqual(nice.select_action(1, state, 0.), 1)
        self.assertEqual(nice.get_stats()['overrides'], 1)

    def test_seeded_detours_are_reproducible(self):
        first, second = make_nice(probability=.4), make_nice(probability=.4)
        state = make_state()
        self.assertEqual([first.select_action(1, state, 0.) for _ in range(100)],
                         [second.select_action(1, state, 0.) for _ in range(100)])


class ActionPolicyTests(unittest.TestCase):
    def test_random_exploration_skips_model_and_nice(self):
        model, nice = Mock(), Mock()
        epsilon = EpsilonAlgo(rng=Random(7), initial=1., minimum=0., decay=.9, log=FakeLog())
        policy = ActionPolicy(model=model, epsilon=epsilon, epsilon_nice=nice, device=torch.device('cpu'))
        self.assertIn(policy.select_action(deque([make_state().observation()]), make_state()), range(3))
        model.assert_not_called()
        nice.select_action.assert_not_called()

    def test_model_suggestion_is_passed_to_nice_with_real_board(self):
        model, nice = Mock(), Mock()
        model.return_value = torch.tensor([[0., 2., 1.]])
        nice.select_action.return_value = 2
        epsilon = EpsilonAlgo(rng=Random(7), initial=0., minimum=0., decay=.9, log=FakeLog())
        policy = ActionPolicy(model=model, epsilon=epsilon, epsilon_nice=nice, device=torch.device('cpu'))
        state = make_state()
        self.assertEqual(policy.select_action(deque([state.observation()] * 4), state), 2)
        self.assertEqual(model.call_args.args[0].shape, (4, 23))
        nice.select_action.assert_called_once_with(1, state, 0.)


if __name__ == '__main__':
    unittest.main()
