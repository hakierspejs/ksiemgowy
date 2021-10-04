#!/usr/bin/env python3

import datetime
import unittest

from ksiemgowy.mbankmail import MbankAction

import ksiemgowy.current_report_builder as M


HAKIERSPEJS_ACC_NO = (
    "d66afcd5d08d61a5678dd3dd3fbb6b2f84985c5add8306e6b3a1c2df0e85f840"
)

LANDLORD_ACC_NO = (
    "5c0de18baddf47952002df587685dea519f06b639051ea3e4749ef058f6782bf"
)


class SecondCurrentReportBuilderTestCase(unittest.TestCase):

    def test_system(self):
        now = datetime.datetime(2021, 9, 4, 12, 14, 6, 812646)

        expenses = [
            MbankAction(
                in_acc_no=HAKIERSPEJS_ACC_NO,
                out_acc_no=LANDLORD_ACC_NO,
                amount_pln=800.0,
                in_person="b5d99033edf432cf08ab35d3e47cfeb4e7af370cd3f",
                in_desc="09564e96eabee7aaddac31c2b7dc11ffe23ca3be4bb",
                balance="3575,04",
                timestamp="2021-09-01 17:19",
                action_type="out_transfer",
            ),
            MbankAction(
                in_acc_no=HAKIERSPEJS_ACC_NO,
                out_acc_no=LANDLORD_ACC_NO,
                amount_pln=177.5,
                in_person="b5d99033edf432cfb35d3e47cfeb4e7af370cd3f",
                in_desc="c66a1e94465f724a5a893af5ce8e38666d3fe304",
                balance="3575,04",
                timestamp="2021-09-01 17:15",
                action_type="out_transfer",
            ),
        ]
        mbank_actions = [
            MbankAction(
                in_acc_no="totallyFake",
                out_acc_no=HAKIERSPEJS_ACC_NO,
                amount_pln=1000.0,
                in_person="alsoFake",
                in_desc="fakeDesc",
                balance="2137,37",
                timestamp="2021-09-02 03:37",
                action_type="in_transfer",
            )
        ]

        corrections: M.T_CORRECTIONS = {
            "ACCOUNT_CORRECTIONS": {"Konto Jacka": 0.0},
            "MONTHLY_INCOME_CORRECTIONS": {},
            "MONTHLY_EXPENSE_CORRECTIONS": {},
        }

        current_report = M.get_current_report(
            now, expenses, mbank_actions, corrections
        )

        expected_output = {
            "dues_total_lastmonth": 1000.0,
            "dues_last_updated": "02-09-2021",
            "dues_num_subscribers": 1,
            "extra_monthly_reservations": 2000,
            "balance_so_far": 2222.5,
            "balances_by_account_labels": {
                "Konto stowarzyszenia": 22.5,
                "Konto Jacka": 2200.0,
            },
            "monthly": {
                "Wydatki": {
                    "2021-09": {
                        "Czynsz": 800.0,
                        "Media (głównie prąd) i "
                        "inne rozliczenia w zw. z lokalem": 177.5,
                    }
                },
                "Przychody": {
                    "2021-09": {"Suma": 1000.0},
                    "2020-06": {"Suma": 200},
                    "2020-07": {"Suma": 200},
                    "2020-08": {"Suma": 200},
                    "2020-09": {"Suma": 200},
                    "2020-10": {"Suma": 200},
                    "2020-11": {"Suma": 200},
                    "2020-12": {"Suma": 200},
                    "2021-01": {"Suma": 200},
                    "2021-02": {"Suma": 200},
                    "2021-03": {"Suma": 200},
                    "2021-04": {"Suma": 200},
                },
                "Bilans": {
                    "2020-08": {"Suma": 200},
                    "2020-11": {"Suma": 200},
                    "2020-07": {"Suma": 200},
                    "2021-03": {"Suma": 200},
                    "2020-09": {"Suma": 200},
                    "2020-06": {"Suma": 200},
                    "2020-12": {"Suma": 200},
                    "2020-10": {"Suma": 200},
                    "2021-04": {"Suma": 200},
                    "2021-01": {"Suma": 200},
                    "2021-02": {"Suma": 200},
                    "2021-09": {"Suma": 22.5},
                },
                "Saldo": {
                    "2020-06": {"Suma": 200},
                    "2020-07": {"Suma": 400},
                    "2020-08": {"Suma": 600},
                    "2020-09": {"Suma": 800},
                    "2020-10": {"Suma": 1000},
                    "2020-11": {"Suma": 1200},
                    "2020-12": {"Suma": 1400},
                    "2021-01": {"Suma": 1600},
                    "2021-02": {"Suma": 1800},
                    "2021-03": {"Suma": 2000},
                    "2021-04": {"Suma": 2200},
                    "2021-09": {"Suma": 2222.5},
                },
            },
        }

        self.assertEqual(expected_output, current_report)
