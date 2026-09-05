import unittest

from snake_lab.configuration import (
    ConfigurationError,
    simulation_config_template,
)


class ConfigTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = simulation_config_template()
        self.defaults = {
            "epochs": 100,
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
                    "closer_to_food": 0.1,
                    "further_from_food": -0.1,
                },
            },
            "model": {
                "hidden_size": 192,
                "layers": 3,
                "dropout": 0.1,
            },
            "training": {
                "sequence_length": 8,
                "batch_size": 64,
                "replay_max_frames": 150000,
                "learning_rate": 0.002,
                "gamma": 0.96,
                "tau": 0.001,
                "max_gradient_norm": 1.0,
            },
            "epsilon": {
                "initial": 0.96,
                "minimum": 0.0,
                "decay": 0.97,
            },
        }

    def test_default_epochs_are_applied(self) -> None:
        self.assertEqual(self.template.resolve({}), self.defaults)

    def test_submitted_epochs_override_the_default(self) -> None:
        expected = {**self.defaults, "epochs": 2500}
        self.assertEqual(self.template.resolve({"epochs": 2500}), expected)

    def test_epoch_boundaries_are_accepted(self) -> None:
        for epochs in (50, 5000):
            with self.subTest(epochs=epochs):
                expected = {**self.defaults, "epochs": epochs}
                self.assertEqual(
                    self.template.resolve({"epochs": epochs}), expected
                )

    def test_epochs_outside_range_are_rejected(self) -> None:
        for epochs in (49, 5001):
            with self.subTest(epochs=epochs):
                with self.assertRaises(ConfigurationError):
                    self.template.resolve({"epochs": epochs})

    def test_non_integer_epochs_are_rejected(self) -> None:
        for epochs in (100.5, True, "100"):
            with self.subTest(epochs=epochs):
                with self.assertRaises(ConfigurationError):
                    self.template.resolve({"epochs": epochs})

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
                "game": {"rewards": {"food": 20}},
                "model": {"hidden_size": 64},
                "training": {"batch_size": 32},
            }
        )

        self.assertEqual(resolved["game"]["rewards"]["food"], 20)
        self.assertEqual(resolved["game"]["rewards"]["wall"], -10.0)
        self.assertEqual(resolved["model"]["hidden_size"], 64)
        self.assertEqual(resolved["model"]["layers"], 3)
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
                        "batch_size": 64,
                        "replay_max_frames": 255,
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
