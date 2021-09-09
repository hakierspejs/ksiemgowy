import unittest

import ksiemgowy.__main__ as main
from ksiemgowy.mbankmail import MbankAction


class EntrypointTestCase(unittest.TestCase):
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
        msg = main.build_confirmation_mail(
            fromaddr="from@address",
            toaddr="to_address",
            mbank_action=mbank_action,
            emails={},
            mbank_anonymization_key=b"ad",
        )

        print(msg)
        self.assertEqual(msg["To"], "to_address")
