import unittest

from snake_lab.configuration import (
    ConfigurationError,
    simulation_config_template,
)


class ConfigTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = simulation_config_template()

    def test_default_epochs_are_applied(self) -> None:
        self.assertEqual(self.template.resolve({}), {"epochs": 1500})

    def test_submitted_epochs_override_the_default(self) -> None:
        self.assertEqual(
            self.template.resolve({"epochs": 2500}), {"epochs": 2500}
        )

    def test_epoch_boundaries_are_accepted(self) -> None:
        for epochs in (100, 5000):
            with self.subTest(epochs=epochs):
                self.assertEqual(
                    self.template.resolve({"epochs": epochs}),
                    {"epochs": epochs},
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


if __name__ == "__main__":
    unittest.main()
