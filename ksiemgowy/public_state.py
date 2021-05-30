import logging
import dateutil.parser
import sqlalchemy


import ksiemgowy.mbankmail

LOGGER = logging.getLogger(__name__)


class PublicState:
    def __init__(self, db_uri):
        self.db = sqlalchemy.create_engine(db_uri)
        metadata = sqlalchemy.MetaData(self.db)

        self.mbank_actions = sqlalchemy.Table(
            "mbank_actions",
            metadata,
            sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column("mbank_action", sqlalchemy.JSON),
        )

        self.expenses = sqlalchemy.Table(
            "expenses",
            metadata,
            sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column("mbank_action", sqlalchemy.JSON),
        )

        try:
            self.mbank_actions.create()
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
        ):
            pass

        try:
            self.expenses.create()
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

    def was_imap_id_already_handled(self, imap_id):
        for entry in self.observed_email_ids.select().execute().fetchall():
            LOGGER.debug(
                "was_imap_id_already_handled: %r vs %r", imap_id, entry.imap_id
            )
            if entry.imap_id == imap_id:
                return True
        return False

    def mark_imap_id_already_handled(self, imap_id):
        LOGGER.debug("mark_imap_id_already_handled(%r)", imap_id)
        self.observed_email_ids.insert(None).execute(imap_id=imap_id)

    def acc_no_to_email(self, notification_type):
        ret = {}
        for entry in self.in_acc_no_to_email.select().execute().fetchall():
            if entry["notify_" + notification_type] == "y":
                ret[entry["in_acc_no"]] = entry["email"]

        return ret

    def list_mbank_actions(self):
        for entry in self.mbank_actions.select().execute().fetchall():
            ret = entry.mbank_action
            ret["timestamp"] = dateutil.parser.parse(ret["timestamp"])
            ret["amount_pln"] = float(ret["amount_pln"].replace(",", "."))
            yield ksiemgowy.mbankmail.MbankAction(**ret)

    def add_mbank_action(self, mbank_action):
        self.mbank_actions.insert(None).execute(mbank_action=mbank_action)

    def add_expense(self, mbank_action):
        self.expenses.insert(None).execute(mbank_action=mbank_action)

    def list_expenses(self):
        for entry in self.expenses.select().execute().fetchall():
            ret = entry.mbank_action
            ret["timestamp"] = dateutil.parser.parse(ret["timestamp"])
            # FIXME: use fractions.fraction instead?
            ret["amount_pln"] = float(ret["amount_pln"].replace(",", "."))
            yield ksiemgowy.mbankmail.MbankAction(**ret)
