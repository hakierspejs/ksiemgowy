import unittest

import ksiemgowy.mbankmail


class MailParserTestCase(unittest.TestCase):
    def test_mail_parser(self):
        with open("docs/przykladowy_zalacznik_mbanku.html", "rb") as f:
            s = f.read()
        parsed = ksiemgowy.mbankmail.parse_mbank_html(s)
        expected = {
            "actions": [
                ksiemgowy.mbankmail.MbankAction(
                    in_acc_no="3511...075800",
                    out_acc_no="81089394",
                    amount_pln="200,00",
                    in_person="JACEK WIELEMBOREK UL",
                    in_desc="SKŁADKA CZŁO...",
                    balance="796,03",
                    timestamp="2021-05-07 01:50",
                    action_type="in_transfer",
                )
            ]
        }
        self.assertEqual(parsed, expected)
