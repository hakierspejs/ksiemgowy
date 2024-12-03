"""This module describes data structures used in ksiemgowy."""

# This is here because we're accessing _mapping attribute of a row object
# pylint: disable=protected-access

import logging
import datetime
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
        metadata = sqlalchemy.MetaData()

        self.bank_actions = sqlalchemy.Table(
            "bank_actions",
            metadata,
            sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column("sender_acc_no", sqlalchemy.String),
            sqlalchemy.Column("out_acc_no", sqlalchemy.String),
            sqlalchemy.Column("amount_pln", sqlalchemy.Float, index=True),
            sqlalchemy.Column("in_person", sqlalchemy.String),
            sqlalchemy.Column("in_desc", sqlalchemy.String),
            sqlalchemy.Column("balance", sqlalchemy.Float),
            sqlalchemy.Column("timestamp", sqlalchemy.String),
            sqlalchemy.Column("action_type", sqlalchemy.String),
        )

        try:
            self.bank_actions.create(bind=self.database)
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
        ):
            pass

        self.sender_acc_no_to_email = sqlalchemy.Table(
            "sender_acc_no_to_email",
            metadata,
            sqlalchemy.Column(
                "sender_acc_no", sqlalchemy.String, primary_key=True
            ),
            sqlalchemy.Column("email", sqlalchemy.String),
            sqlalchemy.Column(
                "notify_arrived", sqlalchemy.String, default="y"
            ),
            sqlalchemy.Column(
                "notify_overdue", sqlalchemy.String, default="y"
            ),
            sqlalchemy.Column(
                "notify_overdue_no_earlier_than",
                sqlalchemy.DateTime,
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
            self.sender_acc_no_to_email.create(bind=self.database)
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
        ):
            pass

        try:
            self.observed_email_ids.create(bind=self.database)
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
        ):
            pass

        self.connection = self.database.connect()

    def was_imap_id_already_handled(self, imap_id: str) -> bool:
        """Tells whether a given IMAP ID was already processed by ksiemgowy."""
        with self.connection.begin():
            entries = self.connection.execute(
                self.observed_email_ids.select().where(
                    self.observed_email_ids.c.imap_id == imap_id
                )
            ).fetchone()
            return bool(entries)

    def mark_imap_id_already_handled(self, imap_id: str) -> None:
        """Marks a given IMAP ID as already processed by ksiemgowy."""
        LOGGER.debug("mark_imap_id_already_handled(%r)", imap_id)
        with self.connection.begin():
            self.connection.execute(
                self.observed_email_ids.insert(), {"imap_id": imap_id}
            )

    def get_email_for_sender_acc_no(self, sender_acc_no: str) -> Optional[str]:
        """Returns an e-mail address for a given sender_acc_no."""

        with self.connection.begin():
            row = self.connection.execute(
                self.sender_acc_no_to_email.select().where(
                    self.sender_acc_no_to_email.c.sender_acc_no == sender_acc_no
                )
            ).fetchone()

            if row:
                ret: str = row._mapping["email"]
                return ret
            return None

    def get_potentially_overdue_accounts(
        self, now: datetime.datetime
    ) -> Dict[str, str]:
        """Returns a list of accounts that might be overdue and can be
        notified."""
        ret = {}
        cols = self.sender_acc_no_to_email.c
        with self.connection.begin():
            for entry in self.connection.execute(
                self.sender_acc_no_to_email.select().where(
                    sqlalchemy.or_(
                        cols.notify_overdue_no_earlier_than.is_(None),
                        cols.notify_overdue_no_earlier_than < now,
                    )
                )
            ).mappings():
                if entry["notify_overdue"] == "y":
                    ret[entry["sender_acc_no"]] = entry["email"]

            return ret

    def postpone_next_notification(
        self, sender_acc_no: str, now: datetime.datetime
    ) -> None:
        """Postpone next overdue notification for an account with a given
        sender_acc_no."""
        cols = self.sender_acc_no_to_email.c
        with self.connection.begin():
            row = self.connection.execute(
                self.sender_acc_no_to_email.select().where(
                    cols.sender_acc_no == sender_acc_no
                )
            ).fetchone()

            base_date = now
            if row is None:
                raise ValueError(f"Account {sender_acc_no} not found in DB.")
            if row._mapping["notify_overdue_no_earlier_than"] is not None:
                base_date = row._mapping["notify_overdue_no_earlier_than"]
            new_date = base_date + datetime.timedelta(days=3, hours=5)

            self.connection.execute(
                self.sender_acc_no_to_email.update()
                .where(self.sender_acc_no_to_email.c.sender_acc_no == sender_acc_no)
                .values(notify_overdue_no_earlier_than=new_date)
            )

    def list_positive_transfers(self) -> Iterator[MbankAction]:
        """Returns a generator that lists all positive transfers that were
        observed so far."""
        with self.connection.begin():
            for entry in self.connection.execute(
                self.bank_actions.select().where(
                    self.bank_actions.c.amount_pln > 0
                )
            ).mappings():
                entry = {k: v for k, v in dict(entry).items() if k != "id"}
                yield ksiemgowy.mbankmail.MbankAction(**entry)

    def add_positive_transfer(self, positive_action: MbankAction) -> None:
        """Adds a positive transfer to the database."""
        with self.connection.begin():
            self.connection.execute(
                self.bank_actions.insert(), positive_action.asdict()
            )

    def add_expense(self, bank_action: MbankAction) -> None:
        """Adds an expense to the database."""
        bank_action.amount_pln *= -1
        with self.connection.begin():
            self.connection.execute(
                self.bank_actions.insert(), **bank_action.asdict()
            )

    def list_expenses(self) -> Iterator[MbankAction]:
        """Returns a generator that lists all expenses transfers that were
        observed so far."""
        with self.connection.begin():
            for entry in self.connection.execute(
                self.bank_actions.select().where(
                    self.bank_actions.c.amount_pln < 0
                )
            ).mappings():
                entry = {k: v for k, v in dict(entry).items() if k != "id"}
                bank_action = ksiemgowy.mbankmail.MbankAction(**entry)
                bank_action.amount_pln *= -1
                yield bank_action
