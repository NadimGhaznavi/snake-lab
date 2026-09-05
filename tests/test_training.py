import math
import unittest

import torch
import torch.nn as nn

from constants.DNNet import DNetDef
from snake_lab.memory import ReplayMemory, Transition
from snake_lab.model import RNNModel
from snake_lab.trainer import Trainer


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
        self.target = target.detach().clone()
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
            batch_size=1,
            max_frames=10,
            min_episodes=1,
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
        self.assertEqual(criterion.shapes, (torch.Size([1, 2]), torch.Size([1, 2])))
        self.assertEqual(criterion.target[-1, -1].item(), 2.0)
        self.assertEqual(trainer.get_average_loss(), loss)
        self.assertIsNone(trainer.get_average_loss())


if __name__ == "__main__":
    unittest.main()
