import unittest

from snakelab.server.Configuration import (
    ConfigurationError,
    simulation_config_template,
)


class ConfigTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = simulation_config_template()
        self.defaults = {
            "epochs": 500,
            "seed": 1970,
            "game": {
                "board_width": 20,
                "board_height": 20,
                "initial_snake_length": 3,
                "max_moves_multiplier": 100,
                "rewards": {
                    "food": 10.0,
                    "wall": -10.0,
                    "snake": -10.0,
                    "max_moves": -10.0,
                    "empty": 0.0,
                    "closer_to_food": 1,
                    "further_from_food": -1,
                },
            },
            "model": {
                "type": "rnn",
                "heads": 4,
                "hidden_size": 224,
                "layers": 4,
                "dropout": 0.1,
            },
            "training": {
                "sequence_length": 8,
                "batch_size": 24,
                "replay_max_frames": 100000,
                "learning_rate": 0.0021,
                "gamma": 0.96,
                "tau": 0.001,
                "max_gradient_norm": 1.0,
            },
            "epsilon": {
                "initial": 0.96,
                "minimum": 0.0,
                "decay": 0.97,
            },
            "epsilon_nice": {"probability": 0.005, "steps": 20},
        }

    def test_default_epochs_are_applied(self) -> None:
        self.assertEqual(self.template.resolve({}), self.defaults)

    def test_submitted_episode_counts_are_preserved(self) -> None:
        for epochs in (50, 500, 1500, 2500, 5000):
            with self.subTest(epochs=epochs):
                self.assertEqual(self.template.resolve({"epochs": epochs})["epochs"], epochs)

    def test_non_integer_epochs_are_rejected(self) -> None:
        for epochs in (100.5, True, "100"):
            with self.subTest(epochs=epochs):
                with self.assertRaises(ConfigurationError):
                    self.template.resolve({"epochs": epochs})

    def test_non_positive_epochs_are_rejected(self):
        for epochs in (0, -1):
            with self.subTest(epochs=epochs):
                with self.assertRaisesRegex(ConfigurationError, r'\$\.epochs'):
                    self.template.resolve({"epochs": epochs})
        self.assertEqual(self.template.resolve({"epochs": 1})["epochs"], 1)

    def test_fractional_reward_configuration_preserves_submitted_values(self):
        rewards = dict(food=12.5, wall=-15.5, snake=-11.25, max_moves=-4.5,
                       empty=-.01, closer_to_food=.1, further_from_food=-.1)
        resolved = self.template.resolve({"game": {"rewards": rewards}})
        self.assertEqual(resolved["game"]["rewards"], rewards)

    def test_reward_signs_types_and_finiteness_are_validated(self):
        for name in self.defaults["game"]["rewards"]:
            wrong_sign = -1 if name in ("food", "closer_to_food") else 1
            for value in (wrong_sign, True, "1", float('nan'), float('inf'), -float('inf')):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(ConfigurationError, rf'\$\.game\.rewards\.{name}'):
                        self.template.resolve({"game": {"rewards": {name: value}}})

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.template.resolve({"unknown": True})

    def test_epsilon_defaults_can_be_partially_overridden(self) -> None:
        resolved = self.template.resolve({"epsilon": {"decay": 0.9}})

        self.assertEqual(
            resolved["epsilon"],
            {"initial": 0.96, "minimum": 0.0, "decay": 0.9},
        )

    def test_invalid_epsilon_values_are_rejected(self) -> None:
        cases = (
            {"initial": -0.1},
            {"initial": 1.1},
            {"minimum": -0.1},
            {"minimum": 1.1},
            {"decay": 0.0},
            {"decay": 1.1},
        )
        for epsilon in cases:
            with self.subTest(epsilon=epsilon):
                with self.assertRaises(ConfigurationError):
                    self.template.resolve({"epsilon": epsilon})

    def test_unknown_epsilon_field_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.template.resolve({"epsilon": {"unknown": 0.5}})

    def test_minimum_epsilon_cannot_exceed_initial_epsilon(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.template.resolve(
                {"epsilon": {"initial": 0.2, "minimum": 0.3}}
            )

    def test_nested_runtime_defaults_can_be_partially_overridden(self) -> None:
        resolved = self.template.resolve(
            {
                "game": {"rewards": {"closer_to_food": 3}},
                "model": {"hidden_size": 64},
                "training": {"batch_size": 32},
            }
        )

        self.assertEqual(resolved["game"]["rewards"]["closer_to_food"], 3)
        self.assertEqual(resolved["game"]["rewards"]["wall"], -10.0)
        self.assertEqual(resolved["model"]["hidden_size"], 64)
        self.assertEqual(resolved["model"]["layers"], 4)
        self.assertEqual(resolved["training"]["batch_size"], 32)

    def test_initial_snake_must_fit_on_board(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.template.resolve(
                {
                    "game": {
                        "board_width": 2,
                        "initial_snake_length": 3,
                    }
                }
            )

    def test_replay_must_hold_one_training_batch(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.template.resolve(
                {
                    "training": {
                        "sequence_length": 4,
                        "batch_size": 24,
                        "replay_max_frames": 255,
                    }
                }
            )

    def test_model_selection_and_nice_settings_resolve_from_partial_input(self):
        resolved = self.template.resolve({
            "model": {"type": "transformer", "heads": 8},
            "epsilon_nice": {"probability": 0},
        })
        self.assertEqual(resolved["model"]["type"], "transformer")
        self.assertEqual(resolved["model"]["heads"], 8)
        self.assertEqual(resolved["model"]["hidden_size"], 224)
        self.assertEqual(resolved["epsilon_nice"], {"probability": 0, "steps": 20})

    def test_invalid_new_settings_are_rejected_at_configuration_boundary(self):
        for submitted in (
            {"model": {"type": "invalid"}}, {"model": {"heads": 0}},
            {"model": {"heads": 3}}, {"model": {"heads": True}},
            {"epsilon_nice": {"probability": -.01}},
            {"epsilon_nice": {"probability": 1.01}},
            {"epsilon_nice": {"steps": 0}}, {"epsilon_nice": {"steps": 1.5}},
            {"epsilon_nice": {"steps": True}}, {"epsilon_nice": {"unknown": 1}},
        ):
            with self.subTest(submitted=submitted), self.assertRaises(ConfigurationError):
                self.template.resolve(submitted)


if __name__ == "__main__":
    unittest.main()
