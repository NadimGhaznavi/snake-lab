"""Server-owned v2 validation, including continuous decimal ranges."""
import unittest
from snake_lab.configuration import ConfigTemplate, ConfigurationError, simulation_config_template


class V2ConfigurationTests(unittest.TestCase):
    def test_v2_default_and_continuous_learning_rate(self):
        template = simulation_config_template()
        default = template.resolve({})
        self.assertEqual(default['epochs'], 1500)
        self.assertEqual(default['training']['learning_rate'], .0021)
        for value in (.0005, .005, .002123456):
            self.assertEqual(template.resolve({'training': {'learning_rate': value}})['training']['learning_rate'], value)
        for value in (.00049, .00501, True, '0.0021'):
            with self.assertRaises(ConfigurationError):
                template.resolve({'training': {'learning_rate': value}})

    def test_continuous_epsilon_gamma_and_integer_rewards_are_accepted(self):
        template = simulation_config_template()
        for initial in range(85, 100):
            for decay in range(90, 100):
                template.resolve({'epsilon': {'initial': initial / 100, 'decay': decay / 100}})
        template.resolve({'epsilon': {'initial': .94321, 'decay': .94567}})
        for gamma in range(90, 100):
            template.resolve({'training': {'gamma': gamma / 100}})
        for closer in range(7):
            for further in range(-6, 1):
                template.resolve({'game': {'rewards': {'closer_to_food': closer, 'further_from_food': further}}})

    def test_server_keeps_integer_steps_and_cross_field_validation(self):
        template = simulation_config_template()
        for value in (.94001, .94321):
            template.resolve({'training': {'gamma': value}})
        with self.assertRaises(ConfigurationError):
            template.resolve({'model': {'hidden_size': 65}})
        schema = {'type': 'object', 'properties': {'epsilon': {'type': 'object', 'properties': {
            'initial': {'type': 'number'}, 'minimum': {'type': 'number'}}}}}
        with self.assertRaisesRegex(ConfigurationError, 'cannot exceed'):
            ConfigTemplate(schema).resolve({'epsilon': {'initial': .5, 'minimum': .6}})
