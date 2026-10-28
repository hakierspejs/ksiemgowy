import unittest
from unittest import mock

import ksiemgowy.bookkeeping


class SentryHealthcheckTestCase(unittest.TestCase):
    def setUp(self):
        self.action = mock.Mock()
        self.action.anonymized.return_value = mock.sentinel.anonymized_action

    @mock.patch("ksiemgowy.bookkeeping.urllib.request.urlopen")
    def test_add_positive_action_pings_healthcheck(self, urlopen):
        database = mock.Mock()
        ksiemgowy.bookkeeping.add_positive_action(
            self.action, b"pepper", database, mock.Mock(), False,
            "https://example.invalid/healthcheck",
        )
        database.add_positive_transfer.assert_called_once_with(
            mock.sentinel.anonymized_action
        )
        urlopen.assert_called_once_with(
            "https://example.invalid/healthcheck", timeout=10
        )

    @mock.patch("ksiemgowy.bookkeeping.urllib.request.urlopen")
    def test_add_positive_action_does_not_ping_without_url(self, urlopen):
        database = mock.Mock()
        ksiemgowy.bookkeeping.add_positive_action(
            self.action, b"pepper", database, mock.Mock(), False, None
        )
        database.add_positive_transfer.assert_called_once()
        urlopen.assert_not_called()

    @mock.patch("ksiemgowy.bookkeeping.urllib.request.urlopen", side_effect=OSError)
    def test_healthcheck_failure_does_not_fail_bookkeeping(self, _urlopen):
        database = mock.Mock()
        ksiemgowy.bookkeeping.add_positive_action(
            self.action, b"pepper", database, mock.Mock(), False,
            "https://example.invalid/healthcheck",
        )
        database.add_positive_transfer.assert_called_once()
