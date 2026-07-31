import unittest

import ksiemgowy.models

from ksiemgowy.mbankmail import MbankAction
from ksiemgowy.models import transactional


def build_action(action_type, amount_pln=10.0):
    return MbankAction(
        recipient_acc_no="recipient",
        sender_acc_no="sender",
        amount_pln=amount_pln,
        in_person="person",
        in_desc="desc",
        balance=1000.0,
        timestamp="2026-07-30 12:00:00",
        action_type=action_type,
    )


class TransactionalTestCase(unittest.TestCase):
    def test_refuses_to_wrap_a_generator_function(self):
        """Wrapping a generator function is always a mistake: calling it only
        builds the generator, so the transaction opens and closes before a
        single row is read. Fail at decoration time rather than leaking a
        transaction at runtime."""

        with self.assertRaises(TypeError):

            @transactional
            def a_generator(self):  # pylint: disable=unused-argument
                yield 1


class KsiemgowyDBTransactionTestCase(unittest.TestCase):
    def setUp(self):
        self.database = ksiemgowy.models.KsiemgowyDB("sqlite://")
        self.database.add_positive_transfer(build_action("in_transfer"))

    def test_listing_expenses_leaves_no_transaction_behind(self):
        """list_expenses() used to autobegin a transaction that nobody ever
        committed, poisoning the connection for every later caller."""
        list(self.database.list_expenses())

        self.assertFalse(self.database.connection.in_transaction())

    def test_listing_positive_transfers_leaves_no_transaction_behind(self):
        list(self.database.list_positive_transfers())

        self.assertFalse(self.database.connection.in_transaction())

    def test_expenses_then_positive_transfers(self):
        """Regression test for the exact ordering get_expected_balance_before()
        uses. It raised:

            InvalidRequestError: This connection has already initialized a
            SQLAlchemy Transaction() object via begin() or autobegin; can't
            call begin() here unless rollback() or commit() is called first.
        """
        list(self.database.list_expenses())
        positive_transfers = list(self.database.list_positive_transfers())

        self.assertEqual(len(positive_transfers), 1)

    def test_positive_transfers_then_expenses(self):
        """The order homepage_updater.maybe_update_dues() uses."""
        list(self.database.list_positive_transfers())
        expenses = list(self.database.list_expenses())

        self.assertEqual(expenses, [])

    def test_listings_can_be_interleaved(self):
        """Both listings materialise before returning, so holding on to one
        while consuming the other must not matter."""
        expenses = self.database.list_expenses()
        positive_transfers = self.database.list_positive_transfers()

        self.assertEqual(list(expenses), [])
        self.assertEqual(len(list(positive_transfers)), 1)
