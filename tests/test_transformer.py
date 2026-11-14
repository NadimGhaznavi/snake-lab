"""Sequence-model contracts, causality, and real Transformer training."""

import math
import unittest

import torch

from snakelab.constants.DNNet import DNetDef
from snakelab.nn.ReplayMemory import ReplayMemory, Transition
from snakelab.nn.RNNModel import RNNModel
from snakelab.nn.Trainer import Trainer
from snakelab.nn.TransformerModel import TransformerModel
from tests.test_training import FakeLog


def make_model(model_type=TransformerModel, *, seed=7, layers=2, dropout=0):
    options = dict(seed=seed, hidden_size=8, dropout=dropout, layers=layers, log=FakeLog())
    if model_type is TransformerModel:
        options.update(heads=2, max_sequence_length=8)
    return model_type(**options)


class SequenceModelTests(unittest.TestCase):
    def test_shapes_and_final_values_for_both_models(self):
        for model_type in (RNNModel, TransformerModel):
            model = make_model(model_type).eval()
            for shape in ((23,), (4, 23), (2, 4, 23)):
                with self.subTest(model=model_type, shape=shape):
                    inputs = torch.randn(shape)
                    sequence = model.forward_sequence(inputs)
                    self.assertEqual(sequence.shape, (2 if len(shape) == 3 else 1,
                                                      4 if len(shape) > 1 else 1, 3))
                    torch.testing.assert_close(model(inputs), sequence[:, -1])

    def test_invalid_dimensions_features_and_empty_sequences(self):
        for model_type in (RNNModel, TransformerModel):
            model = make_model(model_type)
            for shape in ((), (2, 3, 4, 23), (2, 4, 51), (2, 0, 23)):
                with self.subTest(model=model_type, shape=shape), self.assertRaises(ValueError):
                    model(torch.zeros(shape))

    def test_same_seed_reproduces_parameters_and_outputs(self):
        states = torch.randn(2, 4, 23)
        for model_type in (RNNModel, TransformerModel):
            first, second = make_model(model_type).eval(), make_model(model_type).eval()
            for left, right in zip(first.parameters(), second.parameters()):
                torch.testing.assert_close(left, right, rtol=0, atol=0)
            torch.testing.assert_close(first(states), second(states), rtol=0, atol=0)

    def test_causal_prefix_cannot_see_future_frames(self):
        states = torch.randn(2, 6, 23)
        changed = states.clone()
        changed[:, 3:] = torch.randn(2, 3, 23) * 50
        model = make_model().eval()
        # Exercise both autograd and PyTorch's optimized inference path.
        expected = model.forward_sequence(states)[:, :3]
        torch.testing.assert_close(model.forward_sequence(changed)[:, :3], expected)
        with torch.inference_mode():
            torch.testing.assert_close(model.forward_sequence(changed)[:, :3], expected)
        states.requires_grad_()
        model.forward_sequence(states)[:, :3].sum().backward()
        self.assertEqual(torch.count_nonzero(states.grad[:, 3:]).item(), 0)

    def test_positions_distinguish_reordered_history(self):
        model = make_model().eval()
        states = torch.randn(1, 4, 23)
        reordered = states[:, [2, 1, 0, 3]]
        self.assertFalse(torch.allclose(model(states), model(reordered)))

    def test_encoder_layers_are_initialized_independently(self):
        model = make_model()
        first, second = model.encoder.layers
        self.assertFalse(torch.equal(first.self_attn.in_proj_weight,
                                     second.self_attn.in_proj_weight))

    def test_reset_changes_weights_and_preserves_fixed_buffers(self):
        model = make_model()
        weights = model.encoder.layers[0].self_attn.in_proj_weight.detach().clone()
        positions, mask = model.position_encoding.clone(), model.causal_mask.clone()
        model.reset_parameters()
        self.assertFalse(torch.equal(weights, model.encoder.layers[0].self_attn.in_proj_weight))
        torch.testing.assert_close(model.position_encoding, positions)
        torch.testing.assert_close(model.causal_mask, mask)

    def test_context_limit_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'sequence length'):
            make_model()(torch.zeros(9, 23))

    def test_transformer_updates_weights_and_target_from_replay(self):
        replay = ReplayMemory(state_size=DNetDef.INPUT_SIZE, sequence_length=4,
                              batch_size=2, max_frames=16, seed=7, log=FakeLog())
        for index in range(8):
            replay.append(Transition(
                state=(float(index),) * 23, action=index % 3, reward=1.,
                next_state=(float(index + 1),) * 23, done=index == 7,
            ))
        model = make_model(dropout=0.1)
        trainer = Trainer(model=model, replay=replay, device=torch.device('cpu'),
                          learning_rate=0.002, gamma=.96, tau=.1,
                          max_gradient_norm=1., log=FakeLog())
        before = model.input_layer.weight.detach().clone()
        target_before = trainer.target_model.input_layer.weight.detach().clone()
        self.assertTrue(math.isfinite(trainer.train()))
        self.assertFalse(torch.equal(before, model.input_layer.weight))
        self.assertFalse(torch.equal(target_before, trainer.target_model.input_layer.weight))
        self.assertTrue(all(p.grad is None for p in trainer.target_model.parameters()))
        trainer.reset()
        self.assertFalse(trainer.target_model.training)
        for online, target in zip(model.parameters(), trainer.target_model.parameters()):
            torch.testing.assert_close(online, target)


if __name__ == '__main__':
    unittest.main()
