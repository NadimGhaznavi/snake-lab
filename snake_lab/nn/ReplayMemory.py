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
from snake_lab.utils.MyLog import MyLog


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
    """Observations [B,T,F] and final-transition supervision [B].

    Replay-owned buffers are overwritten by the next successful sample().
    Consume synchronously or copy the arrays to retain a batch.
    """

    states: np.ndarray
    actions: np.ndarray
    rewards: np.ndarray
    next_states: np.ndarray
    dones: np.ndarray


@dataclass(frozen=True, slots=True)
class _Episode:
    """N transitions backed by one contiguous array of N + 1 observations."""

    states: np.ndarray
    actions: np.ndarray
    rewards: np.ndarray
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
        self._eligible_episodes: list[_Episode] = []
        self._cumulative_windows: list[int] = []
        self._total_windows = 0
        self._current: list[Transition] = []
        self._frame_count = 0
        self._batch_states = np.empty(
            (batch_size, sequence_length, state_size), dtype=np.float32
        )
        self._batch_next_states = np.empty_like(self._batch_states)
        self._batch_actions = np.empty(batch_size, dtype=np.int64)
        self._batch_rewards = np.empty(batch_size, dtype=np.float32)
        self._batch_dones = np.empty(batch_size, dtype=np.bool_)
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
        """Append contiguous transitions, finalizing on a terminal transition.

        Within an episode, each state must be the preceding next_state.
        This internal caller invariant is covered by tests, not runtime checks.
        """
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
            [transition.state for transition in self._current]
            + [self._current[-1].next_state],
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
        dones = np.asarray(
            [transition.done for transition in self._current],
            dtype=np.bool_,
        )
        episode = _Episode(
            states=states,
            actions=actions,
            rewards=rewards,
            dones=dones,
        )
        self._episodes.append(episode)
        self._frame_count += episode.size
        self._current.clear()

        while self._frame_count > self.max_frames:
            removed = self._episodes.popleft()
            self._frame_count -= removed.size

        # Completed episodes stay unchanged until the next finalization.
        self._eligible_episodes = [
            episode
            for episode in self._episodes
            if episode.size >= self.sequence_length
        ]
        window_counts = [
            episode.size - self.sequence_length + 1
            for episode in self._eligible_episodes
        ]
        self._cumulative_windows = list(accumulate(window_counts))
        self._total_windows = (
            self._cumulative_windows[-1] if self._cumulative_windows else 0
        )

    def sample(self) -> ReplayBatch | None:
        """Sample windows uniformly into buffers valid until the next sample."""
        if self._total_windows < self.batch_size:
            return None

        window_ids = self._rng.sample(
            range(self._total_windows), self.batch_size
        )
        states = self._batch_states
        actions = self._batch_actions
        rewards = self._batch_rewards
        next_states = self._batch_next_states
        dones = self._batch_dones

        for batch_index, window_id in enumerate(window_ids):
            episode_index = bisect_right(self._cumulative_windows, window_id)
            previous_total = (
                self._cumulative_windows[episode_index - 1]
                if episode_index else 0
            )
            start = window_id - previous_total
            end = start + self.sequence_length
            transition_index = end - 1
            episode = self._eligible_episodes[episode_index]
            states[batch_index] = episode.states[start:end]
            actions[batch_index] = episode.actions[transition_index]
            rewards[batch_index] = episode.rewards[transition_index]
            next_states[batch_index] = episode.states[start + 1:end + 1]
            dones[batch_index] = episode.dones[transition_index]

        return ReplayBatch(
            states=states,
            actions=actions,
            rewards=rewards,
            next_states=next_states,
            dones=dones,
        )
