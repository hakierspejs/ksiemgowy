import contextlib
import email

import unittest
import unittest.mock as mock

import ksiemgowy.__main__ as ksiemgowy_main
from ksiemgowy.mbankmail import MbankAction


class ScheduleMock:
    def every(self, *args, **kwargs):

        class inner_inner_class:
            def do(self, fn, *args, **kwargs):
                fn(*args, **kwargs)

        class inner_class:

            hour = inner_inner_class()
            hours = inner_inner_class()

        return inner_class()


class EntrypointTestCase(unittest.TestCase):

    def build_mail_mock(self, messages=None):

        """Generates a mock that fakes imaplib interface, returning e-mails
        from a given iterator. Not my proudest hack. Apologies!"""

        def mail_fetch_mock(mail, _):
            return None, [(None, mail)]

        if messages is None:
            messages = []
        mail_connection_mock = mock.Mock()
        messages_mock = mock.Mock()
        messages_mock.split.return_value = messages
        mail_connection_mock.search.return_value = (None, [messages_mock])
        mail_connection_mock.fetch.side_effect = mail_fetch_mock
        mail_mock = mock.Mock()
        mail_mock.imap_connect.return_value = mail_connection_mock

        def send_message_mock(*args, **kwargs):
            print('message sent.')

        @contextlib.contextmanager
        def smtp_login_mock(*args, **kwargs):
            server_mock = mock.Mock()
            server_mock.send_message.side_effect = send_message_mock
            yield server_mock

        mail_mock.smtp_login = smtp_login_mock

        return mail_mock

    def run_entrypoint(self, messages):
        mail_mock = self.build_mail_mock(messages)

        config_mock = ksiemgowy_main.KsiemgowyConfig(
            database_uri='',
            deploy_key_path='',
            accounts=[
                ksiemgowy_main.KsiemgowyAccount(
                    mail_config=mail_mock, acc_number='81089394')
            ], mbank_anonymization_key=b'')
        database_mock = mock.Mock()
        database_mock.list_positive_transfers.return_value = []
        database_mock.acc_no_to_email.return_value = {}
        database_mock.was_imap_id_already_handled.return_value = False
        ksiemgowy_main.main(config_mock, database_mock, mock.Mock(),
                            ScheduleMock(), lambda: False)

    def test_entrypoint_doesnt_crash(self):

        with open(
                'docs/przykladowy_zalacznik_mbanku.eml', 'rb',
        ) as f:
            self.run_entrypoint([f.read()])

    def test_build_confirmation_mail_copies_email_if_not_in_mapping(self):
        mbank_action = MbankAction(
            in_acc_no="a",
            out_acc_no="b",
            amount_pln="100",
            in_person="asd",
            in_desc="e",
            balance="100",
            timestamp="2021-09-09 22:39:11.099772",
            action_type="in_transfer",
        )
        msg = ksiemgowy_main.build_confirmation_mail(
            fromaddr="from@address",
            toaddr="to_address",
            mbank_action=mbank_action,
            emails={},
            mbank_anonymization_key=b"ad",
        )
        self.assertEqual(msg["To"], "to_address")
