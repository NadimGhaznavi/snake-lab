"""Batched recurrent Double DQN training for SnakeLab."""

from copy import deepcopy

import torch

from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from constants.DNNet import DRNN
from constants.DSnakeLab import DSnakeLab
from constants.DTrainer import DTrainer
from snake_lab.memory import ReplayMemory
from snake_lab.model import RNNModel
from utils.MyLog import MyLog


class Trainer:
    """Train an RNN model from dense replay-memory batches."""

    def __init__(
        self,
        *,
        model: RNNModel,
        replay: ReplayMemory,
        device: torch.device,
        learning_rate: float = DRNN.LEARNING_RATE,
        gamma: float = DRNN.GAMMA,
        tau: float = DRNN.TAU,
        max_gradient_norm: float | None = 1.0,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        if learning_rate <= 0:
            raise ValueError("learning_rate must be greater than zero")
        if not 0 <= gamma <= 1:
            raise ValueError("gamma must be in the range [0, 1]")
        if not 0 < tau <= 1:
            raise ValueError("tau must be in the range (0, 1]")
        if max_gradient_norm is not None and max_gradient_norm <= 0:
            raise ValueError("max_gradient_norm must be greater than zero")

        self.device = device
        self.model = model.to(self.device)
        self.target_model = deepcopy(self.model).to(self.device)
        self.target_model.eval()
        self.replay = replay
        self.gamma = gamma
        self.tau = tau
        self.max_gradient_norm = max_gradient_norm
        self.optimizer = DTrainer.OPTIM(
            self.model.parameters(), lr=learning_rate
        )
        self.criterion = DTrainer.CRITERION()
        self.log = log or MyLog(
            client_id=DModule.TRAINER,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=False,
        )
        self._losses: list[float] = []
        self._has_logged_shape = False
        self.log.info(
            f"Initialized trainer: learning_rate={learning_rate}, "
            f"gamma={gamma}, tau={tau}"
        )

    def train(self) -> float | None:
        """Train once from a fixed-shape replay batch."""
        batch = self.replay.sample()
        if batch is None:
            return None
        if not self._has_logged_shape:
            self.log.debug(
                f"Training with batch={batch.states.shape[0]}, "
                f"sequence={batch.states.shape[1]}"
            )
            self._has_logged_shape = True

        states = torch.as_tensor(
            batch.states, dtype=torch.float32, device=self.device
        )
        actions = torch.as_tensor(
            batch.actions, dtype=torch.long, device=self.device
        )
        rewards = torch.as_tensor(
            batch.rewards, dtype=torch.float32, device=self.device
        )
        next_states = torch.as_tensor(
            batch.next_states, dtype=torch.float32, device=self.device
        )
        dones = torch.as_tensor(
            batch.dones, dtype=torch.bool, device=self.device
        )

        self.model.train()
        predicted_all = self.model.forward_sequence(states)
        predicted = predicted_all.gather(
            2, actions.unsqueeze(-1)
        ).squeeze(-1)

        with torch.no_grad():
            self.model.eval()
            next_actions = self.model.forward_sequence(next_states).argmax(
                dim=2, keepdim=True
            )
            self.model.train()
            target_all = self.target_model.forward_sequence(next_states)
            target_next = target_all.gather(2, next_actions).squeeze(-1)
            target = rewards + self.gamma * target_next * (~dones)

        loss = self.criterion(predicted, target)
        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        if self.max_gradient_norm is not None:
            torch.nn.utils.clip_grad_norm_(
                self.model.parameters(), self.max_gradient_norm
            )
        self.optimizer.step()
        self._soft_update_target()

        loss_value = float(loss.item())
        self._losses.append(loss_value)
        return loss_value

    def _soft_update_target(self) -> None:
        with torch.no_grad():
            for target_parameter, parameter in zip(
                self.target_model.parameters(), self.model.parameters()
            ):
                target_parameter.lerp_(parameter, self.tau)

    def get_average_loss(self) -> float | None:
        """Return and clear the accumulated mean loss."""
        if not self._losses:
            return None
        average = sum(self._losses) / len(self._losses)
        self._losses.clear()
        return average

    def reset(self) -> None:
        """Reset optimizer and target-network state."""
        self.optimizer.state.clear()
        self.target_model.load_state_dict(self.model.state_dict())
        self.target_model.eval()
