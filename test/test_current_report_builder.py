#!/usr/bin/env python3

import datetime
import unittest

from ksiemgowy.mbankmail import MbankAction

from ksiemgowy.config import ReportBuilderConfig
import ksiemgowy.current_report_builder as M


HAKIERSPEJS_ACC_NO = (
    "d66afcd5d08d61a5678dd3dd3fbb6b2f84985c5add8306e6b3a1c2df0e85f840"
)

LANDLORD_ACC_NO = (
    "5c0de18baddf47952002df587685dea519f06b639051ea3e4749ef058f6782bf"
)


class SecondReportBuilderBuilderTestCase(unittest.TestCase):
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
        positive_actions = [
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

        current_builder_config = ReportBuilderConfig(
            account_labels={
                "d66afcd5d08d61a5678dd3dd3f"
                "bb6b2f84985c5add8306e6b3a1c2df0e85f840": "Konto Jacka"
            },
            corrections_by_label={"Konto Jacka": 0.0},
            monthly_income_corrections={},
            monthly_expense_corrections={},
            first_200pln_d33tah_due_date=datetime.datetime.now(),
            last_200pln_d33tah_due_date=datetime.datetime.now(),
            extra_monthly_reservations_started_date=datetime.datetime.now(),
        )

        current_report = M.get_current_report(
            now, expenses, positive_actions, current_builder_config
        )

        expected_output = {
            "dues_total_lastmonth": 1000.0,
            "dues_last_updated": "02-09-2021",
            "dues_num_subscribers": 1,
            "extra_monthly_reservations": 0,
            "balance_so_far": 222.5,
            "balances_by_account_labels": {"Konto Jacka": 222.5},
            "monthly": {
                "Wydatki": {
                    "2021-09": {
                        "Czynsz": 800.0,
                        "Media (głównie prąd) i inne rozliczenia w zw. z lokalem": 177.5,
                    }
                },
                "Przychody": {
                    "2021-09": {"Suma": 1000.0},
                    "2021-10": {"Suma": 200},
                },
                "Bilans": {
                    "2021-10": {"Suma": 200},
                    "2021-09": {"Suma": 22.5},
                },
                "Saldo": {
                    "2021-09": {"Suma": 22.5},
                    "2021-10": {"Suma": 222.5},
                },
            },
        }

        self.assertEqual(expected_output, current_report)
