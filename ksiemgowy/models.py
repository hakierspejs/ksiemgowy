"""This module describes data structures used in ksiemgowy."""

import logging
from typing import Dict, Iterator, Optional

import sqlalchemy

import ksiemgowy.mbankmail
from ksiemgowy.mbankmail import MbankAction

LOGGER = logging.getLogger(__name__)


class KsiemgowyDB:
    """A class that groups together all models that describe the state of
    ksiemgowy."""

    def __init__(self, database_uri: str) -> None:
        """Initializes the database, creating tables if they don't exist."""
        self.database = sqlalchemy.create_engine(database_uri)
        metadata = sqlalchemy.MetaData(self.database)

        self.bank_actions = sqlalchemy.Table(
            "bank_actions",
            metadata,
            sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column("in_acc_no", sqlalchemy.String),
            sqlalchemy.Column("out_acc_no", sqlalchemy.String),
            sqlalchemy.Column("amount_pln", sqlalchemy.Float, index=True),
            sqlalchemy.Column("in_person", sqlalchemy.String),
            sqlalchemy.Column("in_desc", sqlalchemy.String),
            sqlalchemy.Column("balance", sqlalchemy.Float),
            sqlalchemy.Column("timestamp", sqlalchemy.String),
            sqlalchemy.Column("action_type", sqlalchemy.String),
        )

        try:
            self.bank_actions.create()
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
        ):
            pass

        self.in_acc_no_to_email = sqlalchemy.Table(
            "in_acc_no_to_email",
            metadata,
            sqlalchemy.Column(
                "in_acc_no", sqlalchemy.String, primary_key=True
            ),
            sqlalchemy.Column("email", sqlalchemy.String),
            sqlalchemy.Column(
                "notify_arrived", sqlalchemy.String, default="y"
            ),
            sqlalchemy.Column(
                "notify_overdue", sqlalchemy.String, default="y"
            ),
            sqlalchemy.Column(
                "notify_overdue_no_earlier_than", sqlalchemy.DateTime
            ),
            sqlalchemy.Column("is_member", sqlalchemy.String, default="n"),
        )

        self.observed_email_ids = sqlalchemy.Table(
            "observed_email_ids",
            metadata,
            sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column("imap_id", sqlalchemy.String, unique=True),
        )

        try:
            self.in_acc_no_to_email.create()
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
        ):
            pass

        try:
            self.observed_email_ids.create()
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
        ):
            pass

    def was_imap_id_already_handled(self, imap_id: str) -> bool:
        """Tells whether a given IMAP ID was already processed by ksiemgowy."""
        entries = (
            self.observed_email_ids.select()
            .where(self.observed_email_ids.c.imap_id == imap_id)
            .execute()
            .fetchone()
        )
        return bool(entries)

    def mark_imap_id_already_handled(self, imap_id: str) -> None:
        """Marks a given IMAP ID as already processed by ksiemgowy."""
        LOGGER.debug("mark_imap_id_already_handled(%r)", imap_id)
        self.observed_email_ids.insert(None).execute(imap_id=imap_id)

    def get_email_for_in_acc_no(self, in_acc_no: str) -> Optional[str]:
        """Builds a mapping between banking accounts an e-mail addresses for
        people interested in a given type of a notification."""

        row = (
            self.in_acc_no_to_email.select()
            .where(self.in_acc_no_to_email.c.in_acc_no == in_acc_no)
            .execute()
            .fetchone()
        )

        if row:
            ret: str = row['email']
            return ret
        return None

    def get_potentially_overdue_accounts(self) -> Dict[str, str]:
        """Builds a mapping between banking accounts an e-mail addresses for
        people interested in a given type of a notification."""
        ret = {}
        for entry in self.in_acc_no_to_email.select().execute().fetchall():
            if entry["notify_overdue"] == "y":
                ret[entry["in_acc_no"]] = entry["email"]

        return ret

    def list_positive_transfers(self) -> Iterator[MbankAction]:
        """Returns a generator that lists all positive transfers that were
        observed so far."""
        for entry in (
            self.bank_actions.select()
            .where(self.bank_actions.c.amount_pln > 0)
            .execute()
            .fetchall()
        ):
            entry = {k: v for k, v in dict(entry).items() if k != "id"}
            yield ksiemgowy.mbankmail.MbankAction(**entry)

    def add_positive_transfer(self, positive_action: MbankAction) -> None:
        """Adds a positive transfer to the database."""
        self.bank_actions.insert(None).execute(**positive_action.asdict())

    def add_expense(self, bank_action: MbankAction) -> None:
        """Adds an expense to the database."""
        bank_action.amount_pln *= -1
        self.bank_actions.insert(None).execute(**bank_action.asdict())

    def list_expenses(self) -> Iterator[MbankAction]:
        """Returns a generator that lists all expenses transfers that were
        observed so far."""
        for entry in (
            self.bank_actions.select()
            .where(self.bank_actions.c.amount_pln < 0)
            .execute()
            .fetchall()
        ):
            entry = {k: v for k, v in dict(entry).items() if k != "id"}
            bank_action = ksiemgowy.mbankmail.MbankAction(**entry)
            bank_action.amount_pln *= -1
            yield bank_action
