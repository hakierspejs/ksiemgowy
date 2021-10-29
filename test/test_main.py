import datetime
import contextlib
import email

import unittest
import unittest.mock as mock
import typing as T

import ksiemgowy.__main__ as ksiemgowy_main
import ksiemgowy.models
import ksiemgowy.config
import ksiemgowy.bookkeeping
from ksiemgowy.mbankmail import MbankAction


def run_immediately(_, fn, args, kwargs):
    fn(*args, **kwargs)


class KsiemgowySystemTestCase(unittest.TestCase):
    def setUp(self):
        """Generates a mock that fakes imaplib interface, returning e-mails
        from a given iterator. Not my proudest hack. Apologies!"""

        self.sent_messages: T.List[email.message.Message] = []
        self.incoming_messages: T.List[bytes] = []

        def mail_fetch_mock(mail, _):
            return None, [(None, mail)]

        def return_messages(*args, **kwargs):
            return self.incoming_messages

        mail_connection_mock = mock.Mock()
        messages_mock = mock.Mock()
        messages_mock.split.side_effect = return_messages
        mail_connection_mock.search.return_value = (None, [messages_mock])
        mail_connection_mock.fetch.side_effect = mail_fetch_mock
        mail_mock = mock.Mock()
        mail_mock.imap_connect.return_value = mail_connection_mock

        def send_message_mock(msg):
            self.sent_messages.append(msg)

        @contextlib.contextmanager
        def smtp_login_mock(*args, **kwargs):
            server_mock = mock.Mock()
            server_mock.send_message.side_effect = send_message_mock
            yield server_mock

        mail_mock.smtp_login = smtp_login_mock

        self.config_mock = ksiemgowy.config.KsiemgowyConfig(
            database_uri="",
            accounts=[
                ksiemgowy.config.KsiemgowyAccount(
                    mail_config=mail_mock, acc_number="81089394"
                )
            ],
            mbank_anonymization_key=b"",
            should_send_mail=True,
            homepage_updater_config=ksiemgowy.config.HomepageUpdaterConfig(
                deploy_key_path="",
                git_url="",
                dues_file_path="/",
                graphite_host="127.0.0.1",
                graphite_port=31337,
            ),
            report_builder_config=ksiemgowy.config.ReportBuilderConfig(
                account_labels={
                    "d66afcd5d08d61a5678dd3dd3fbb6b2f84985c5add8306e6b3a1c2df0e85f840": "Konto Jacka"
                },
                corrections_by_label={"Konto Jacka": 0.0},
                monthly_income_corrections={},
                monthly_expense_corrections={},
            ),
        )
        self.database_mock = ksiemgowy.models.KsiemgowyDB("sqlite://")

    def run_entrypoint(
        self, positive_actions_fixtures=None, in_acc_no_to_email_fixtures=None
    ):

        if positive_actions_fixtures:
            for action in positive_actions_fixtures:
                self.database_mock.add_positive_transfer(action)

        if in_acc_no_to_email_fixtures:
            for (
                in_acc_no,
                email_address,
            ) in in_acc_no_to_email_fixtures.items():
                self.database_mock.in_acc_no_to_email.insert(None).execute(
                    in_acc_no=in_acc_no, email=email_address
                )

        ksiemgowy_main.main(
            self.config_mock,
            self.database_mock,
            mock.Mock(),
            run_immediately,
            mock.Mock(),
        )

    def test_entrypoint_sends_a_message(self):

        with open(
            "docs/przykladowy_zalacznik_mbanku.eml",
            "rb",
        ) as f:
            self.incoming_messages = [f.read()]
            self.run_entrypoint()
            self.assertEqual(len(self.sent_messages), 1)

    def test_running_entrypoint_twice_sends_a_single_message(self):

        with open(
            "docs/przykladowy_zalacznik_mbanku.eml",
            "rb",
        ) as f:
            self.incoming_messages = [f.read()]
            self.run_entrypoint()
            self.run_entrypoint()
            self.assertEqual(len(self.sent_messages), 1)

    def test_entrypoint_does_nothing_when_inbox_is_empty(self):

        self.run_entrypoint()
        self.assertEqual(len(self.sent_messages), 0)

    def test_entrypoint_sends_no_reminder_if_user_isnt_overdue(self):

        now = datetime.datetime.now()
        some_time_ago = now - datetime.timedelta(days=20)

        self.run_entrypoint(
            [
                MbankAction(
                    in_acc_no="a",
                    out_acc_no="b",
                    amount_pln=100.0,
                    in_person="asd",
                    in_desc="e",
                    balance="100",
                    timestamp=str(some_time_ago),
                    action_type="in_transfer",
                )
            ],
            {"a": "example@example.com"},
        )
        self.assertEqual(len(self.sent_messages), 0)

    def test_entrypoint_sends_a_reminder_if_somebody_is_overdue(self):

        now = datetime.datetime.now()
        some_time_ago = now - datetime.timedelta(days=40)

        self.run_entrypoint(
            [
                MbankAction(
                    in_acc_no="a",
                    out_acc_no="b",
                    amount_pln=100.0,
                    in_person="asd",
                    in_desc="e",
                    balance="100",
                    timestamp=str(some_time_ago),
                    action_type="in_transfer",
                )
            ],
            {"a": "example@example.com"},
        )
        self.assertEqual(len(self.sent_messages), 1)


class BuildConfirmationMailTestCase(unittest.TestCase):
    def test_build_confirmation_mail_copies_email_if_not_in_mapping(self):
        positive_action = MbankAction(
            in_acc_no="a",
            out_acc_no="b",
            amount_pln=100.0,
            in_person="asd",
            in_desc="e",
            balance="100",
            timestamp="2021-09-09 22:39:11.099772",
            action_type="in_transfer",
        )
        msg = ksiemgowy.bookkeeping.build_confirmation_mail(
            fromaddr="from@address",
            toaddr="to_address",
            positive_action=positive_action,
            emails={},
            mbank_anonymization_key=b"ad",
        )
        self.assertEqual(msg["To"], "to_address")
