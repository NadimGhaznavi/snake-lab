"""SnakeLab simulation runtime."""

from __future__ import annotations

import asyncio
import hashlib
import random
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

import torch

from constants.DGame import DGameDef
from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from constants.DSnakeLab import DSnakeLab
from snake_lab.configuration import simulation_config_template
from snake_lab.epsilon import EpsilonAlgo
from snake_lab.game import Outcome, RewardConfig
from snake_lab.tensor_game import OUTCOMES, TensorSnakeGame
from snake_lab.tensor_memory import TensorReplayMemory
from snake_lab.model import RNNModel
from snake_lab.runtime_control import SimulationControl
from snake_lab.telemetry import FrameTelemetry
from snake_lab.trainer import Trainer
from utils.MyLog import MyLog


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    """Completed state for one independently reproducible episode."""

    episode: int
    seed: int
    score: int
    reward: float
    steps: int
    outcome: Outcome
    epsilon: float
    epsilon_injections: int
    loss: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode,
            "seed": self.seed,
            "score": self.score,
            "reward": self.reward,
            "steps": self.steps,
            "outcome": self.outcome.value,
            "epsilon": self.epsilon,
            "epsilon_injections": self.epsilon_injections,
            "loss": self.loss,
        }


@dataclass(slots=True)
class SimulationState:
    """Mutable run-level progress and completed episode results."""

    total_epochs: int
    completed_epochs: int = 0
    total_steps: int = 0
    high_score: int = 0
    total_reward: float = 0.0
    total_epsilon_injections: int = 0
    last_loss: float | None = None
    episodes: list[EpisodeResult] = field(default_factory=list)

    def record(self, result: EpisodeResult) -> None:
        self.episodes.append(result)
        self.completed_epochs += 1
        self.total_steps += result.steps
        self.high_score = max(self.high_score, result.score)
        self.total_reward += result.reward
        self.total_epsilon_injections += result.epsilon_injections
        self.last_loss = result.loss

    def summary(self) -> dict[str, Any]:
        return {
            "epochs": self.total_epochs,
            "completed_epochs": self.completed_epochs,
            "total_steps": self.total_steps,
            "high_score": self.high_score,
            "total_reward": self.total_reward,
            "epsilon_injections": self.total_epsilon_injections,
            "last_loss": self.last_loss,
        }


EpisodeCallback = Callable[[EpisodeResult, SimulationState], None]
FrameCallback = Callable[[FrameTelemetry], None]


def _derived_seed(master_seed: int, namespace: str, index: int = 0) -> int:
    """Derive a stable independent seed without sharing RNG consumption."""
    material = f"snake-lab-v1:{master_seed}:{namespace}:{index}".encode()
    digest = hashlib.blake2b(material, digest_size=8).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


class Simulator:
    """Execute one isolated, serial SnakeLab simulation."""

    def __init__(
        self,
        config: dict[str, Any],
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        torch_module: Any = torch,
        log: MyLog | None = None,
        on_episode: EpisodeCallback | None = None,
        on_frame: FrameCallback | None = None,
        runtime_control: SimulationControl | None = None,
        frame_enabled: Callable[[], bool] | None = None,
    ) -> None:
        self.config = simulation_config_template().resolve(deepcopy(config))
        self._torch = torch_module
        self._log_file = log_file
        self._provided_log = log
        self._on_episode = on_episode
        self._on_frame = on_frame
        self._frame_enabled = frame_enabled
        self._frame_telemetry_active: bool | None = None
        self.runtime_control = runtime_control or SimulationControl()
        self.log = log or MyLog(
            client_id=DModule.SIMULATOR,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=True,
        )
        if self._torch.cuda.is_available():
            self.device = self._torch.device("cuda")
            device_name = self._torch.cuda.get_device_name(self.device)
            self._location = f"GPU ({device_name})"
        else:
            self.device = self._torch.device("cpu")
            self._location = "CPU"

        self.state = SimulationState(total_epochs=self.config["epochs"])
        self.model: RNNModel | None = None
        self.replay: TensorReplayMemory | None = None
        self.trainer: Trainer | None = None
        self.epsilon: EpsilonAlgo | None = None
        self._started = False

    @property
    def runtime_description(self) -> str:
        return f"Simulation running on {self._location}"

    def probe_runtime(self) -> None:
        """Exercise the selected device and report where work is running."""
        probe = self._torch.ones(1, device=self.device)
        (probe + 1).sum().item()
        if self.device.type == "cuda":
            self._torch.cuda.synchronize(self.device)
        self.log.info(self.runtime_description)

    def _component_log_args(self) -> dict[str, Any]:
        if self._provided_log is not None:
            return {"log": self._provided_log}
        return {"log_file": self._log_file}

    def _setup(self) -> None:
        """Construct all configured runtime components for one run."""
        master_seed = self.config["seed"]
        model_config = self.config["model"]
        training = self.config["training"]
        epsilon = self.config["epsilon"]
        log_args = self._component_log_args()

        self.model = RNNModel(
            seed=_derived_seed(master_seed, "model"),
            hidden_size=model_config["hidden_size"],
            dropout=model_config["dropout"],
            layers=model_config["layers"],
            **log_args,
        )
        self.replay = TensorReplayMemory(
            state_size=DGameDef.OBSERVATION_SIZE,
            sequence_length=training["sequence_length"],
            batch_size=training["batch_size"],
            max_frames=training["replay_max_frames"],
            seed=_derived_seed(master_seed, "replay"),
            device=self.device,
        )
        self.trainer = Trainer(
            model=self.model,
            replay=self.replay,
            device=self.device,
            learning_rate=training["learning_rate"],
            gamma=training["gamma"],
            tau=training["tau"],
            max_gradient_norm=training["max_gradient_norm"],
            **log_args,
        )
        self._exploration_generator = torch.Generator(device=self.device).manual_seed(
            _derived_seed(master_seed, "epsilon")
        )
        self.epsilon = EpsilonAlgo(
            rng=random.Random(_derived_seed(master_seed, "epsilon")),
            initial=epsilon["initial"],
            minimum=epsilon["minimum"],
            decay=epsilon["decay"],
            **log_args,
        )

    def _new_game(self, episode: int) -> TensorSnakeGame:
        game = self.config["game"]
        reward_values = game["rewards"]
        return TensorSnakeGame(
            seed=_derived_seed(self.config["seed"], "episode", episode),
            episode_id=episode,
            grid_size=(game["board_width"], game["board_height"]),
            initial_snake_length=game["initial_snake_length"],
            max_moves_multiplier=game["max_moves_multiplier"],
            rewards=RewardConfig(**reward_values),
            device=self.device,
        )

    def _select_action(
        self, history: torch.Tensor, random_action: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Keep policy input and selected action on the simulation device."""
        if self.model is None:
            raise RuntimeError("simulator components have not been initialized")
        if random_action is not None:
            return random_action
        with torch.no_grad():
            return self.model(history).argmax(dim=1)

    def _exploration_draw(self) -> tuple[torch.Tensor, torch.Tensor]:
        explore = torch.rand(
            (1,), device=self.device, generator=self._exploration_generator,
        ) < self.epsilon.current
        action = torch.randint(
            DGameDef.ACTION_COUNT, (1,), device=self.device,
            generator=self._exploration_generator,
        )
        return explore, action

    async def _run_episode(self, episode: int) -> EpisodeResult:
        if self.replay is None or self.trainer is None or self.epsilon is None:
            raise RuntimeError("simulator components have not been initialized")

        game = self._new_game(episode)
        observation = game.observe()
        history = observation[:, None, :].repeat(
            1, self.config["training"]["sequence_length"], 1,
        )
        episode_epsilon = self.epsilon.current
        injections = torch.zeros(1, device=self.device, dtype=torch.long)
        explore, random_action = self._exploration_draw()
        exploring = bool(explore.item())
        self.model.eval()

        while True:
            action = self._select_action(history, random_action if exploring else None)
            injections += explore.long()
            next_observation = game.step(action)
            self.replay.append(
                observation, action, game.reward, next_observation, game.done,
            )
            # A single scalar read schedules the episode boundary and the next
            # exploration branch. Actions/observations/replay never leave device.
            explore, random_action = self._exploration_draw()
            control = int((game.done.long() + 2 * explore.long()).item())
            done, exploring = bool(control & 1), bool(control & 2)
            frame_active = self._on_frame is not None and (
                self._frame_enabled is None or self._frame_enabled()
            )
            if frame_active != self._frame_telemetry_active:
                self._frame_telemetry_active = frame_active
                status = "enabled" if frame_active else "disabled"
                self.log.info(f"Per-move telemetry {status}")
            if frame_active:
                self._on_frame(
                    FrameTelemetry.from_step(
                        episode=episode, action=int(action.item()),
                        result=game.export_step(),
                    )
                )
            if done:
                await asyncio.sleep(0)
                break
            observation = next_observation
            history = torch.cat((history[:, 1:, :], observation[:, None, :]), dim=1)
            await self.runtime_control.checkpoint()

        self.replay.finish_episode()
        loss = self.trainer.train()
        injection_count = int(injections.item())
        self.epsilon.record_injections(injection_count)
        result = EpisodeResult(
            episode=episode, seed=game.seed, score=int(game.score.item()),
            reward=float(game.total_reward.item()), steps=int(game.moves.item()),
            outcome=OUTCOMES[int(game.outcome.item())], epsilon=episode_epsilon,
            epsilon_injections=injection_count, loss=loss,
        )
        self.epsilon.episode_completed()
        return result

    async def run(self) -> SimulationState:
        """Run every configured episode and return the run-level state."""
        if self._started:
            raise RuntimeError("a Simulator instance can only run once")
        self._started = True
        self.probe_runtime()
        await asyncio.sleep(0)
        self._setup()
        await asyncio.sleep(0)

        for episode in range(1, self.config["epochs"] + 1):
            await self.runtime_control.checkpoint(apply_delay=False)
            result = await self._run_episode(episode)
            self.state.record(result)
            if self._on_episode is not None:
                self._on_episode(result, self.state)
            if episode % 100 == 0 or episode == self.config["epochs"]:
                self.log.info(
                    f"Completed epoch {episode}/{self.config['epochs']}: "
                    f"score={result.score}, high_score={self.state.high_score}"
                )
            if episode < self.config["epochs"]:
                await self.runtime_control.checkpoint()

        return self.state
