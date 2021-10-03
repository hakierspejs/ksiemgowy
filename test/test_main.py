import unittest
import unittest.mock as mock

import ksiemgowy.__main__ as ksiemgowy_main
from ksiemgowy.mbankmail import MbankAction


class EntrypointTestCase(unittest.TestCase):

    def test_entrypoint_doesnt_crash(self):

        mail_search_mock = mock.Mock()
        mail_search_mock.search.return_value = [None, ['']]
        mail_mock = mock.Mock()
        mail_mock.imap_connect.return_value = mail_search_mock
        config_mock = ksiemgowy_main.KsiemgowyConfig(
            database_uri='',
            deploy_key_path='',
            accounts=[
                ksiemgowy_main.KsiemgowyAccount(
                    mail_config=mail_mock, acc_number='')
            ], mbank_anonymization_key='')
        ksiemgowy_main.main(config_mock, mock.Mock(), mock.Mock(),
                       mock.Mock(), lambda: False)

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

        print(msg)
        self.assertEqual(msg["To"], "to_address")
