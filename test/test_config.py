import unittest

import ksiemgowy.config


class ConfigTestCase(unittest.TestCase):
    def test_example_config_ok(self):
        with open("docs/example_config.yaml", encoding="utf8") as f:
            ksiemgowy.config.load_config(f)
