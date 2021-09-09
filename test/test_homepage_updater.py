import unittest

import ksiemgowy.homepage_updater as H


class HomepageUpdaterIntegrationTestCase(unittest.TestCase):
    def test_is_local_state_newer_returns_true_if_local_data_is_newer(self):
        self.assertEqual(
            H.is_local_state_newer(
                remote_state={"dues_last_updated": "10-01-2000"},
                current_report={"dues_last_updated": "11-01-2000"},
            ),
            True,
        )

    def test_is_local_state_newer_returns_false_if_local_data_is_older(self):
        self.assertEqual(
            H.is_local_state_newer(
                remote_state={"dues_last_updated": "12-01-2000"},
                current_report={"dues_last_updated": "11-01-2000"},
            ),
            False,
        )
