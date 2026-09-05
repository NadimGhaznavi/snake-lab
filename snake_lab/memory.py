"""Episode replay with terminal-aligned recurrent chunks."""

from collections import deque
from dataclasses import dataclass
from random import Random

import numpy as np

from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from constants.DSnakeLab import DSnakeLab
from utils.MyLog import MyLog


@dataclass(frozen=True, slots=True)
class Transition:
    """One environment transition stored in replay memory."""

    state: tuple[float, ...]
    action: int
    reward: float
    next_state: tuple[float, ...]
    done: bool


@dataclass(frozen=True, slots=True)
class ReplayBatch:
    """Retained chunks as [chunks, sequence, features] plus per-move targets.

    The chunk count varies with the selected games; batch_size counts games.
    """

    states: np.ndarray
    actions: np.ndarray
    rewards: np.ndarray
    next_states: np.ndarray
    dones: np.ndarray


@dataclass(frozen=True, slots=True)
class _Episode:
    states: np.ndarray
    actions: np.ndarray
    rewards: np.ndarray
    next_states: np.ndarray
    dones: np.ndarray

    @property
    def size(self) -> int:
        return int(self.actions.size)


class ReplayMemory:
    """Sample complete games uniformly after a stored-episode warmup."""

    def __init__(
        self,
        *,
        state_size: int,
        sequence_length: int,
        batch_size: int,
        max_frames: int,
        seed: int,
        min_episodes: int = 30,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        for name, value in (
            ("state_size", state_size),
            ("sequence_length", sequence_length),
            ("batch_size", batch_size),
            ("max_frames", max_frames),
            ("min_episodes", min_episodes),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if max_frames < sequence_length * max(batch_size, min_episodes):
            raise ValueError(
                "max_frames must hold sequence_length * "
                "max(batch_size, min_episodes)"
            )

        self.state_size = state_size
        self.sequence_length = sequence_length
        self.batch_size = batch_size
        self.max_frames = max_frames
        self.min_episodes = min_episodes
        self._rng = Random(seed)
        self._episodes: deque[_Episode] = deque()
        self._current: list[Transition] = []
        self._frame_count = 0
        self.log = log or MyLog(
            client_id=DModule.REPLAY_MEMORY,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=False,
        )
        self.log.info(
            f"Initialized replay memory: batch={batch_size}, "
            f"sequence={sequence_length}, max_frames={max_frames}, "
            f"min_episodes={min_episodes}"
        )

    @property
    def episode_count(self) -> int:
        return len(self._episodes)

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def append(self, transition: Transition) -> None:
        """Append a transition, finalizing its episode when it is terminal."""
        if not isinstance(transition, Transition):
            raise TypeError("transition must be a Transition")
        if len(transition.state) != self.state_size:
            raise ValueError(f"state must contain {self.state_size} values")
        if len(transition.next_state) != self.state_size:
            raise ValueError(
                f"next_state must contain {self.state_size} values"
            )
        if type(transition.action) is not int or transition.action < 0:
            raise ValueError("action must be a non-negative integer")
        if type(transition.done) is not bool:
            raise TypeError("done must be a boolean")

        self._current.append(transition)
        if transition.done:
            self._finalize_episode()

    def _finalize_episode(self) -> None:
        # Anchor full chunks at the terminal move. Never pad short games.
        if len(self._current) < self.sequence_length:
            self._current.clear()
            return
        prefix = len(self._current) % self.sequence_length
        if prefix:
            del self._current[:prefix]
        states = np.asarray(
            [transition.state for transition in self._current],
            dtype=np.float32,
        )
        actions = np.asarray(
            [transition.action for transition in self._current],
            dtype=np.int64,
        )
        rewards = np.asarray(
            [transition.reward for transition in self._current],
            dtype=np.float32,
        )
        next_states = np.asarray(
            [transition.next_state for transition in self._current],
            dtype=np.float32,
        )
        dones = np.asarray(
            [transition.done for transition in self._current],
            dtype=np.bool_,
        )
        episode = _Episode(
            states=states.reshape(-1, self.sequence_length, self.state_size),
            actions=actions.reshape(-1, self.sequence_length),
            rewards=rewards.reshape(-1, self.sequence_length),
            next_states=next_states.reshape(
                -1, self.sequence_length, self.state_size
            ),
            dones=dones.reshape(-1, self.sequence_length),
        )
        self._episodes.append(episode)
        self._frame_count += episode.size
        self._current.clear()

        while self._frame_count > self.max_frames:
            removed = self._episodes.popleft()
            self._frame_count -= removed.size

    def sample(self) -> ReplayBatch | None:
        """Choose games uniformly and return all their terminal-aligned chunks."""
        if self.episode_count < max(self.min_episodes, self.batch_size):
            return None
        episodes = self._rng.sample(list(self._episodes), self.batch_size)

        def chunks(field: str) -> np.ndarray:
            # Batch size one reuses the stored chunks without copying or
            # reshaping. Consumers must not mutate these replay-owned arrays.
            if len(episodes) == 1:
                return getattr(episodes[0], field)
            return np.concatenate([getattr(episode, field) for episode in episodes])

        return ReplayBatch(
            states=chunks("states"), actions=chunks("actions"),
            rewards=chunks("rewards"), next_states=chunks("next_states"),
            dones=chunks("dones"),
        )
