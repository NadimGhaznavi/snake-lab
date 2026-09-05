import unittest

import torch

from snake_lab.tensor_memory import TensorReplayMemory


class TensorReplayTests(unittest.TestCase):
    device = torch.device("cpu")

    def memory(self, capacity=8, batch=2):
        return TensorReplayMemory(
            state_size=3, sequence_length=2, batch_size=batch,
            max_frames=capacity, seed=7, device=self.device,
        )

    def append_episode(self, memory, values):
        for index, value in enumerate(values):
            state = torch.full((1, 3), float(value), device=self.device)
            memory.append(
                state, torch.tensor([1], device=self.device),
                torch.tensor([0.1], device=self.device), state + 1,
                torch.tensor([index == len(values) - 1], device=self.device),
            )
        memory.finish_episode()

    def test_windows_do_not_cross_episode_boundaries(self):
        memory = self.memory(batch=4)
        self.append_episode(memory, [0, 1, 2])
        self.append_episode(memory, [10, 11, 12])
        batch = memory.sample()
        self.assertEqual(batch.states.shape, (4, 2, 3))
        self.assertEqual(batch.states.device.type, self.device.type)
        self.assertEqual(batch.actions.dtype, torch.long)
        self.assertEqual(batch.dones.dtype, torch.bool)
        self.assertEqual(
            {tuple(row) for row in batch.states[:, :, 0].tolist()},
            {(0, 1), (1, 2), (10, 11), (11, 12)},
        )
        torch.testing.assert_close(batch.next_states, batch.states + 1)

    def test_wraparound_evicts_whole_episodes(self):
        memory = self.memory()
        self.append_episode(memory, [0, 1, 2])
        self.append_episode(memory, [10, 11, 12])
        self.append_episode(memory, [20, 21, 22, 23])
        self.assertEqual(memory.episode_count, 2)
        self.assertEqual(memory.frame_count, 7)
        for _ in range(10):
            batch = memory.sample()
            for row in batch.states[:, :, 0].tolist():
                self.assertIn(tuple(row), {(10, 11), (11, 12), (20, 21), (21, 22), (22, 23)})

    def test_oversized_episode_and_partial_episode_are_not_sampled(self):
        memory = self.memory()
        self.append_episode(memory, list(range(9)))
        self.assertEqual(memory.episode_count, 0)
        self.assertIsNone(memory.sample())
        state = torch.zeros((1, 3), device=self.device)
        memory.append(state, torch.tensor([0], device=self.device), state[:, 0], state, torch.tensor([False], device=self.device))
        self.assertIsNone(memory.sample())
        memory.finish_episode()
        self.assertIsNone(memory.sample())

    def test_sample_is_independent_of_ring_storage(self):
        memory = self.memory()
        self.append_episode(memory, [0, 1, 2, 3])
        batch = memory.sample()
        saved = batch.states.clone()
        self.append_episode(memory, list(range(10, 18)))
        torch.testing.assert_close(batch.states, saved)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA device required")
class CudaTensorReplayTests(TensorReplayTests):
    device = torch.device("cuda")
