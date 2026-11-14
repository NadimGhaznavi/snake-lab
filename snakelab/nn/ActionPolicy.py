"""Compose model inference, ordinary epsilon, and safe exploration."""

from collections.abc import Iterable

import torch

from snakelab.game.GameState import GameState
from snakelab.nn.EpsilonAlgo import EpsilonAlgo
from snakelab.nn.EpsilonNiceAlgo import EpsilonNiceAlgo
from snakelab.nn.SequenceModel import SequenceModel


class ActionPolicy:
    """Choose an action from the complete rolling observation window."""

    def __init__(
        self, *, model: SequenceModel, epsilon: EpsilonAlgo,
        epsilon_nice: EpsilonNiceAlgo, device: torch.device,
    ) -> None:
        self.model = model
        self.epsilon = epsilon
        self.epsilon_nice = epsilon_nice
        self.device = device

    def select_action(self, history: Iterable[tuple[float, ...]], state: GameState) -> int:
        random_action = self.epsilon.maybe_random_action()
        if random_action is not None:
            return random_action

        states = torch.as_tensor(tuple(history), dtype=torch.float32, device=self.device)
        self.model.eval()
        with torch.inference_mode():
            suggested = int(self.model(states).argmax(dim=1).item())
        return self.epsilon_nice.select_action(suggested, state, self.epsilon.current)
