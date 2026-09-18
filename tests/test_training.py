import math
import unittest
from unittest.mock import Mock

import numpy as np

import torch
import torch.nn as nn

from constants.DNNet import DNetDef
from snake_lab.nn.ReplayMemory import ReplayBatch, ReplayMemory, Transition
from snake_lab.nn.RNNModel import RNNModel
from snake_lab.nn.Trainer import Trainer


class FakeLog:
    def info(self, _message: str) -> None:
        pass

    def debug(self, _message: str) -> None:
        pass


class ShapeRecordingLoss(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.shapes: tuple[torch.Size, torch.Size] | None = None

    def forward(
        self, predicted: torch.Tensor, target: torch.Tensor
    ) -> torch.Tensor:
        self.shapes = (predicted.shape, target.shape)
        return torch.square(predicted - target).mean()

class RNNModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = RNNModel(
            seed=7,
            hidden_size=8,
            dropout=0,
            layers=1,
            log=FakeLog(),
        )

    def test_forward_sequence_preserves_batch_and_time(self) -> None:
        states = torch.zeros(2, 4, DNetDef.INPUT_SIZE)
        self.assertEqual(
            self.model.forward_sequence(states).shape,
            (2, 4, DNetDef.OUTPUT_SIZE),
        )

    def test_forward_returns_final_timestep(self) -> None:
        state = torch.zeros(DNetDef.INPUT_SIZE)
        self.assertEqual(
            self.model(state).shape,
            (1, DNetDef.OUTPUT_SIZE),
        )

    def test_wrong_feature_count_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.model.forward_sequence(torch.zeros(2, 4, 3))


class TrainerTests(unittest.TestCase):
    def test_train_consumes_one_dense_batch(self) -> None:
        replay = ReplayMemory(
            state_size=DNetDef.INPUT_SIZE,
            sequence_length=2,
            batch_size=2,
            max_frames=10,
            seed=7,
            log=FakeLog(),
        )
        for index in range(3):
            state = tuple(float(index) for _ in range(DNetDef.INPUT_SIZE))
            replay.append(
                Transition(
                    state=state,
                    action=index % DNetDef.OUTPUT_SIZE,
                    reward=float(index),
                    next_state=tuple(value + 0.5 for value in state),
                    done=index == 2,
                )
            )
        model = RNNModel(
            seed=7,
            hidden_size=8,
            dropout=0,
            layers=1,
            log=FakeLog(),
        )
        trainer = Trainer(
            model=model,
            replay=replay,
            device=torch.device("cpu"),
            learning_rate=0.002,
            gamma=0.96,
            tau=0.001,
            max_gradient_norm=1.0,
            log=FakeLog(),
        )
        criterion = ShapeRecordingLoss()
        trainer.criterion = criterion

        loss = trainer.train()

        self.assertIsNotNone(loss)
        self.assertTrue(math.isfinite(loss))
        self.assertEqual(criterion.shapes, (torch.Size([2]), torch.Size([2])))


class TableModel(nn.Module):
    """Deterministic action values for hand-calculated training examples."""

    def __init__(self, values):
        super().__init__()
        self.values = nn.Parameter(torch.tensor(values, dtype=torch.float32))

    def forward_sequence(self, states):
        return self.values[states[..., 0].long()]


class RecordingHuberLoss(nn.SmoothL1Loss):
    def forward(self, predicted, target):
        self.predicted = predicted.detach().clone()
        self.target = target.detach().clone()
        self.target_requires_grad = target.requires_grad
        return super().forward(predicted, target)


class TrainerCalculationTests(unittest.TestCase):
    def make_trainer(self, tau=0.25):
        # The first timestep is deliberately unlike the last. Only the final
        # action/reward/done should contribute directly to the loss.
        batch = ReplayBatch(
            states=np.array([[[0], [1]], [[2], [3]]], dtype=np.float32),
            actions=np.array([[2, 0], [0, 2]], dtype=np.int64),
            rewards=np.array([[-99, 2], [-88, 3]], dtype=np.float32),
            next_states=np.array([[[4], [5]], [[6], [7]]], dtype=np.float32),
            dones=np.array([[True, False], [False, True]], dtype=np.bool_),
        )
        replay = Mock(spec=ReplayMemory)
        replay.sample.return_value = batch
        model = TableModel([
            [50, 60, 70], [2, 8, 9], [80, 90, 100], [6, 7, 4],
            [40, 30, 20], [1, 9, 2], [40, 30, 20], [8, 2, 1],
        ])
        trainer = Trainer(
            model=model, replay=replay, device=torch.device("cpu"),
            learning_rate=0.01, gamma=0.5, tau=tau,
            max_gradient_norm=None, log=FakeLog(),
        )
        with torch.no_grad():
            trainer.target_model.values[5] = torch.tensor([100., 12., 30.])
            trainer.target_model.values[7] = torch.tensor([200., 300., 400.])
        trainer.criterion = RecordingHuberLoss()
        return trainer

    def test_double_dqn_uses_online_action_and_target_value(self):
        trainer = self.make_trainer()
        loss = trainer.train()
        # Online network chooses action 1; target network values it at 12.
        # Choosing the target's own maximum would incorrectly use 100.
        self.assertEqual(trainer.criterion.target[0].item(), 2 + 0.5 * 12)
        torch.testing.assert_close(trainer.criterion.predicted, torch.tensor([2., 4.]))
        # Huber errors are -6 and +1: mean(5.5, 0.5) = 3.
        self.assertAlmostEqual(loss, 3.0)
        self.assertFalse(trainer.criterion.target_requires_grad)
        self.assertTrue(all(p.grad is None for p in trainer.target_model.parameters()))

    def test_terminal_transition_uses_reward_without_bootstrap(self):
        trainer = self.make_trainer()
        trainer.train()
        # Target values are large, but the final transition ends the episode.
        self.assertEqual(trainer.criterion.target[1].item(), 3.0)

    def test_soft_update_uses_post_optimizer_online_weights(self):
        for tau in (0.25, 1.0):
            with self.subTest(tau=tau):
                trainer = self.make_trainer(tau=tau)
                old_online = trainer.model.values.detach().clone()
                old_target = trainer.target_model.values.detach().clone()
                trainer.train()
                new_online = trainer.model.values.detach()
                self.assertFalse(torch.equal(old_online, new_online))
                expected = (1 - tau) * old_target + tau * new_online
                torch.testing.assert_close(trainer.target_model.values, expected)
                self.assertFalse(trainer.target_model.training)

    def test_no_batch_leaves_models_and_optimizer_untouched(self):
        trainer = self.make_trainer()
        trainer.replay.sample.return_value = None
        online = trainer.model.values.detach().clone()
        target = trainer.target_model.values.detach().clone()
        self.assertIsNone(trainer.train())
        torch.testing.assert_close(trainer.model.values, online)
        torch.testing.assert_close(trainer.target_model.values, target)
        self.assertEqual(len(trainer.optimizer.state), 0)

    def test_target_starts_as_independent_copy_of_online_model(self):
        model = TableModel([[1, 2, 3]])
        trainer = Trainer(
            model=model, replay=Mock(spec=ReplayMemory), device=torch.device("cpu"),
            learning_rate=0.01, gamma=0.5, tau=0.25,
            max_gradient_norm=None, log=FakeLog(),
        )
        torch.testing.assert_close(trainer.model.values, trainer.target_model.values)
        with torch.no_grad():
            trainer.model.values.add_(1)
        torch.testing.assert_close(trainer.target_model.values, torch.tensor([[1., 2., 3.]]))
        self.assertFalse(trainer.target_model.training)


if __name__ == "__main__":
    unittest.main()
