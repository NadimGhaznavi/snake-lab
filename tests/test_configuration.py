import unittest

from snake_lab.configuration import (
    ConfigurationError,
    simulation_config_template,
)


class ConfigTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = simulation_config_template()
        self.defaults = {
            "epochs": 1500,
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
        for epochs in (100, 5000):
            with self.subTest(epochs=epochs):
                expected = {**self.defaults, "epochs": epochs}
                self.assertEqual(
                    self.template.resolve({"epochs": epochs}), expected
                )

    def test_epochs_outside_range_are_rejected(self) -> None:
        for epochs in (99, 5001):
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


if __name__ == "__main__":
    unittest.main()
