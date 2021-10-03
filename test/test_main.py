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

    def test_entrypoint_doesnt_crash(self):

        mail_search_mock = mock.Mock()
        mail_search_mock.search.return_value = [None, ['']]
        mail_mock = mock.Mock()
        mail_mock.imap_connect.return_value = mail_search_mock
        smtp_login_mock = mock.Mock()
        smtp_login_mock.__enter__ = mock.Mock()
        smtp_login_mock.__exit__ = mock.Mock()
        mail_mock.smtp_login.return_value = smtp_login_mock

        config_mock = ksiemgowy_main.KsiemgowyConfig(
            database_uri='',
            deploy_key_path='',
            accounts=[
                ksiemgowy_main.KsiemgowyAccount(
                    mail_config=mail_mock, acc_number='')
            ], mbank_anonymization_key='')
        database_mock = mock.Mock()
        database_mock.list_positive_transfers.return_value = []
        ksiemgowy_main.main(config_mock, database_mock, mock.Mock(),
                            ScheduleMock(), lambda: False)

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
