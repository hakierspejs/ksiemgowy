import unittest

import ksiemgowy.models

from ksiemgowy.mbankmail import MbankAction


def build_action(action_type, amount_pln=10.0):
    return MbankAction(
        sender_acc_no="sender",
        recipient_acc_no="recipient",
        amount_pln=amount_pln,
        in_person="person",
        in_desc="desc",
        balance=1000.0,
        timestamp="2026-07-30 12:00:00",
        action_type=action_type,
    )


class KsiemgowyDBTestCase(unittest.TestCase):
    def setUp(self):
        self.database = ksiemgowy.models.KsiemgowyDB("sqlite://")

    def test_add_expense_stores_a_listable_expense(self):
        """add_expense() splats the action into Connection.execute() as
        keyword arguments, which SQLAlchemy 2.0 rejects. Every outgoing
        transfer therefore blows up check_for_updates()."""
        self.database.add_expense(build_action("out_transfer"))

        expenses = list(self.database.list_expenses())

        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0].amount_pln, 10.0)
        self.assertEqual(expenses[0].recipient_acc_no, "recipient")
        self.assertEqual(expenses[0].action_type, "out_transfer")

    def test_expenses_are_not_reported_as_positive_transfers(self):
        """Expenses are stored negated, so they must not leak into the
        positive transfer listing (and vice versa)."""
        self.database.add_expense(build_action("out_transfer"))
        self.database.add_positive_transfer(build_action("in_transfer"))

        self.assertEqual(len(list(self.database.list_expenses())), 1)
        self.assertEqual(len(list(self.database.list_positive_transfers())), 1)
