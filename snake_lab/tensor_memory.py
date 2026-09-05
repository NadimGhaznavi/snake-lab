"""Preallocated device replay with whole-episode retention and tensor sampling."""

from collections import deque
from dataclasses import dataclass

import torch


@dataclass(frozen=True, slots=True)
class TensorReplayBatch:
    states: torch.Tensor
    actions: torch.Tensor
    rewards: torch.Tensor
    next_states: torch.Tensor
    dones: torch.Tensor


class TensorReplayMemory:
    def __init__(
        self, *, state_size: int, sequence_length: int, batch_size: int,
        max_frames: int, seed: int, device: torch.device,
    ) -> None:
        if min(state_size, sequence_length, batch_size, max_frames) <= 0:
            raise ValueError("replay dimensions must be positive")
        if max_frames < sequence_length * batch_size:
            raise ValueError("max_frames must hold at least one complete training batch")
        self.device = torch.device(device)
        self.sequence_length, self.batch_size = sequence_length, batch_size
        self.max_frames = max_frames
        self.generator = torch.Generator(device=self.device).manual_seed(seed)
        # The environment axis is explicit even though phase one runs one game.
        shape = (max_frames, 1, state_size)
        self.states = torch.empty(shape, device=self.device)
        self.next_states = torch.empty_like(self.states)
        self.actions = torch.empty((max_frames, 1), device=self.device, dtype=torch.long)
        self.rewards = torch.empty((max_frames, 1), device=self.device)
        self.dones = torch.empty((max_frames, 1), device=self.device, dtype=torch.bool)
        self._written = 0
        self._episode_start = 0
        self._episodes: deque[tuple[int, int]] = deque()
        self._starts = torch.empty(0, device=self.device, dtype=torch.long)
        self._cumulative = torch.empty_like(self._starts)
        self._total_windows = 0
        self._dirty = False

    @property
    def episode_count(self) -> int:
        return len(self._episodes)

    @property
    def frame_count(self) -> int:
        return sum(size for _, size in self._episodes)

    @torch.no_grad()
    def append(
        self, state: torch.Tensor, action: torch.Tensor, reward: torch.Tensor,
        next_state: torch.Tensor, done: torch.Tensor,
    ) -> None:
        index = self._written % self.max_frames
        self.states[index].copy_(state)
        self.next_states[index].copy_(next_state)
        self.actions[index].copy_(action.reshape(1))
        self.rewards[index].copy_(reward.reshape(1))
        self.dones[index].copy_(done.reshape(1))
        self._written += 1
        # Never leave a partially overwritten episode eligible for sampling.
        while self._episodes and self._episodes[0][0] < self._written - self.max_frames:
            self._episodes.popleft()
            self._dirty = True

    def finish_episode(self) -> None:
        size = self._written - self._episode_start
        if 0 < size <= self.max_frames:
            self._episodes.append((self._episode_start, size))
        self._episode_start = self._written
        self._dirty = True

    def _index_windows(self) -> None:
        eligible = [(start, size) for start, size in self._episodes if size >= self.sequence_length]
        starts = [start for start, _ in eligible]
        counts = [size - self.sequence_length + 1 for _, size in eligible]
        self._starts = torch.tensor(starts, device=self.device, dtype=torch.long)
        self._cumulative = torch.tensor(counts, device=self.device, dtype=torch.long).cumsum(0)
        self._total_windows = sum(counts)
        self._dirty = False

    @torch.no_grad()
    def sample(self) -> TensorReplayBatch | None:
        if self._dirty:
            self._index_windows()
        if self._total_windows < self.batch_size:
            return None
        # Uniform windows without replacement, as in the reference replay.
        windows = torch.randperm(
            self._total_windows, generator=self.generator, device=self.device,
        )[:self.batch_size]
        episodes = torch.bucketize(windows, self._cumulative, right=True)
        previous = torch.cat((self._cumulative.new_zeros(1), self._cumulative[:-1]))
        starts = self._starts[episodes] + windows - previous[episodes]
        indices = (
            starts[:, None] + torch.arange(self.sequence_length, device=self.device)
        ) % self.max_frames
        return TensorReplayBatch(
            states=self.states[indices, 0], actions=self.actions[indices, 0],
            rewards=self.rewards[indices, 0], next_states=self.next_states[indices, 0],
            dones=self.dones[indices, 0],
        )
