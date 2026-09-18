"""Configuration remains the public boundary for schema and application errors."""

from copy import deepcopy
import unittest

from snake_lab.server.Configuration import Configuration, ConfigurationError


class ConfigurationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "epsilon": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "initial": {"type": "number", "default": 0.9},
                        "minimum": {"type": "number", "default": 0.1},
                    },
                },
            },
        }
        self.configuration = Configuration(self.schema)

    def test_defaults_are_merged_without_sharing_mutable_state(self):
        submitted = {"epsilon": {"initial": 0.8}}
        before = deepcopy(submitted)
        resolved = self.configuration.resolve(submitted)
        self.assertEqual(resolved, {"epsilon": {"initial": 0.8, "minimum": 0.1}})
        self.assertEqual(submitted, before)
        resolved["epsilon"]["minimum"] = 0.7
        self.schema["properties"]["epsilon"]["properties"]["minimum"]["default"] = 0.6
        self.assertEqual(self.configuration.resolve({})["epsilon"]["minimum"], 0.1)

    def test_schema_failure_is_exposed_as_configuration_error(self):
        with self.assertRaisesRegex(ConfigurationError, r'\$\.epsilon\.initial') as raised:
            self.configuration.resolve({"epsilon": {"initial": "invalid"}})
        self.assertIsNotNone(raised.exception.__cause__)
        with self.assertRaises(ConfigurationError):
            self.configuration.resolve([])

    def test_schema_valid_values_still_receive_application_checks(self):
        with self.assertRaisesRegex(ConfigurationError, 'cannot exceed initial epsilon'):
            self.configuration.resolve({"epsilon": {"initial": 0.2, "minimum": 0.3}})
