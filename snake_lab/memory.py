"""Fixed-shape, episode-aware replay memory for recurrent training."""

from bisect import bisect_right
from collections import deque
from dataclasses import dataclass
from itertools import accumulate
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
    """Dense, fixed-shape arrays ready for conversion to PyTorch tensors."""

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
        return int(self.actions.shape[0])


class ReplayMemory:
    """Store complete episodes and sample dense recurrent sequences."""

    def __init__(
        self,
        *,
        state_size: int,
        sequence_length: int,
        batch_size: int,
        max_frames: int,
        seed: int,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        for name, value in (
            ("state_size", state_size),
            ("sequence_length", sequence_length),
            ("batch_size", batch_size),
            ("max_frames", max_frames),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if max_frames < sequence_length * batch_size:
            raise ValueError(
                "max_frames must hold at least one complete training batch"
            )

        self.state_size = state_size
        self.sequence_length = sequence_length
        self.batch_size = batch_size
        self.max_frames = max_frames
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
            f"sequence={sequence_length}, max_frames={max_frames}"
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
            states=states,
            actions=actions,
            rewards=rewards,
            next_states=next_states,
            dones=dones,
        )
        self._episodes.append(episode)
        self._frame_count += episode.size
        self._current.clear()

        while self._frame_count > self.max_frames:
            removed = self._episodes.popleft()
            self._frame_count -= removed.size

    def sample(self) -> ReplayBatch | None:
        """Sample uniformly from all in-episode sliding windows."""
        eligible = [
            episode
            for episode in self._episodes
            if episode.size >= self.sequence_length
        ]
        window_counts = [
            episode.size - self.sequence_length + 1 for episode in eligible
        ]
        total_windows = sum(window_counts)
        if total_windows < self.batch_size:
            return None

        cumulative = list(accumulate(window_counts))
        window_ids = self._rng.sample(range(total_windows), self.batch_size)
        states = np.empty(
            (self.batch_size, self.sequence_length, self.state_size),
            dtype=np.float32,
        )
        actions = np.empty(
            (self.batch_size, self.sequence_length), dtype=np.int64
        )
        rewards = np.empty(
            (self.batch_size, self.sequence_length), dtype=np.float32
        )
        next_states = np.empty_like(states)
        dones = np.empty(
            (self.batch_size, self.sequence_length), dtype=np.bool_
        )

        for batch_index, window_id in enumerate(window_ids):
            episode_index = bisect_right(cumulative, window_id)
            previous_total = (
                cumulative[episode_index - 1] if episode_index else 0
            )
            start = window_id - previous_total
            end = start + self.sequence_length
            episode = eligible[episode_index]
            states[batch_index] = episode.states[start:end]
            actions[batch_index] = episode.actions[start:end]
            rewards[batch_index] = episode.rewards[start:end]
            next_states[batch_index] = episode.next_states[start:end]
            dones[batch_index] = episode.dones[start:end]

        return ReplayBatch(
            states=states,
            actions=actions,
            rewards=rewards,
            next_states=next_states,
            dones=dones,
        )
