"""Handles the task of finding out about new wire transfers and notifying the
users once they're observed."""

import math
import datetime
import typing as T
import logging
import imaplib
import email
from email.message import Message
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import holidays  # type: ignore

import ksiemgowy.config
from ksiemgowy.mbankmail import MbankAction, anonymize
from ksiemgowy.models import KsiemgowyDB


LOGGER = logging.getLogger("ksiemgowy.__main__")
POLISH_HOLIDAYS = holidays.Poland()


def build_confirmation_mail(
    fromaddr: str,
    positive_action: MbankAction,
    toaddr: T.Optional[str] = None,
) -> MIMEMultipart:
    """Sends an e-mail confirming that a membership due has arrived and was
    accounted for."""
    msg = MIMEMultipart("alternative")
    msg["From"] = fromaddr
    if toaddr:
        msg["To"] = toaddr
        msg["Cc"] = fromaddr
    else:
        msg["To"] = fromaddr
    msg["Subject"] = "ksiemgowyd: zaksiemgowano przelew! :)"
    message_text = f"""Dziękuję za wspieranie Hakierspejsu! ❤

Twój przelew na kwotę {positive_action.amount_pln} zł z dnia \
{positive_action.timestamp} został pomyślnie zaksięgowany przez Ksiemgowego. \
Wkrótce strona internetowa Hakierspejsu zostanie zaktualizowana, aby \
odzwierciedlać aktualny stan konta.

Wiadomość została wygenerowana automatycznie przez program "ksiemgowy", którego
kod źródłowy dostępny jest tutaj:

https://github.com/hakierspejs/ksiemgowy

Jeśli nie chcesz w przyszłości dostawać tego typu wiadomości, daj znać Jackowi
przez Telegrama, Matriksa albo wyślij oddzielnego maila.
"""
    msg.attach(MIMEText(message_text, "plain", "utf-8"))
    return msg


def gen_unseen_mbank_emails(
    database: KsiemgowyDB, mail: imaplib.IMAP4_SSL, imap_filter: str
) -> T.Iterator[Message]:
    """Connects to imap_server using login and password from the arguments,
    then yields a pair (mail_id_as_str, email_as_eml_string) for each of
    e-mails coming from mBank."""
    mail.select("inbox")
    _, data = mail.search(None, imap_filter)
    mail_ids = data[0]
    id_list = mail_ids.split()
    for mail_id in id_list:
        _, data = mail.fetch(mail_id, "(RFC822)")
        for mail_number, response_part in enumerate(data):
            if not isinstance(response_part, tuple):
                continue
            msg = email.message_from_string(response_part[1].decode())
            mail_key = f'{msg["Date"]}_{mail_number}'
            if database.was_imap_id_already_handled(mail_key):
                continue
            LOGGER.debug("Handling e-mail id: %r", mail_id)
            yield msg
            database.mark_imap_id_already_handled(mail_key)


def apply_autocorrections(
    database: KsiemgowyDB,
    acc_no: str,
    difference: float,
    mbank_anonymization_key: bytes,
    last_action: MbankAction,
) -> None:
    """Create a database entry correcting for a given discrepancy."""
    if difference > 0:

        action = MbankAction(
            recipient_acc_no=acc_no,
            sender_acc_no="AUTOCORRECTION",
            amount_pln=difference,
            in_person="AUTOCORRECTION",
            in_desc="AUTOCORRECTION",
            balance=last_action.balance,
            timestamp=last_action.timestamp,
            action_type="in_transfer",
        )
        database.add_positive_transfer(
            action.anonymized(mbank_anonymization_key)
        )

    else:
        action = MbankAction(
            sender_acc_no=acc_no,
            recipient_acc_no="AUTOCORRECTION",
            amount_pln=-difference,
            in_person="AUTOCORRECTION",
            in_desc="AUTOCORRECTION",
            balance=last_action.balance,
            timestamp=last_action.timestamp,
            action_type="out_transfer",
        )
        database.add_expense(action.anonymized(mbank_anonymization_key))

    LOGGER.debug("*** apply_autocorrections: action=%r", action)


def get_expected_balance_before(
    database: KsiemgowyDB, acc_no: str, before: datetime.datetime
) -> float:
    """Calculates expected balance for a given account, as of given date. Bases
    the calculations on data stored in the database."""
    balance_so_far = 0.0
    for action in database.list_expenses():
        if action.sender_acc_no != acc_no:
            continue
        if action.get_timestamp() > before:
            continue
        balance_so_far -= action.amount_pln

    for action in database.list_positive_transfers():
        if action.recipient_acc_no != acc_no:
            continue
        if action.get_timestamp() > before:
            continue
        balance_so_far += action.amount_pln

    return balance_so_far


def date_acceptable_for_autocorrection(date: datetime.datetime) -> bool:
    """
    Returns a boolean saying whether the given date is acceptable for
    the potential generation of any autocorrections.

    There's a likelihood that autocorrections code triggers too early
    if a transfer was sent during the weekend. This is because
    incoming transfers within the same bank could arrive and trigger
    a notification with a changed balance, resulting in an
    autocorrection because some money was "suspended" because of the
    weekend transfer. Now, on the workday the money would actually
    arrive, adding a transfer for which an autocorrection already
    took place.

    There's also a risk that a day before or after is a holiday and in this
    case we might want to decide to be on the safe side as well. As for
    handling the relationship of any international transfers and their
    holidays, I explicitly refuse to try to handle that. For the use cases
    of Hakierspejs, this already seems to be more than enough.
    """

    if date.weekday() not in [1, 2, 3]:
        return False

    if date.date() in POLISH_HOLIDAYS:
        return False

    day_before = (date - datetime.timedelta(days=1)).date()
    if day_before in POLISH_HOLIDAYS:
        return False

    day_after = (date + datetime.timedelta(days=1)).date()
    if day_after in POLISH_HOLIDAYS:
        return False

    return True


def maybe_apply_autocorrections(
    database: KsiemgowyDB,
    actions_per_accno: T.Dict[str, T.List[MbankAction]],
    mbank_anonymization_key: bytes,
) -> None:
    """For each account that only observed a single transfer in the
    notification e-mail, see if the reported balance contradicts the state
    visible in the system. If it does, attempt to autocorrect the discrepancy.
    """
    for acc_no in actions_per_accno:
        if len(actions_per_accno[acc_no]) != 1:
            continue
        last_action = actions_per_accno[acc_no].pop()
        if not date_acceptable_for_autocorrection(last_action.get_timestamp()):
            continue
        actual_balance = last_action.balance
        hashed_acc_no = anonymize(acc_no, mbank_anonymization_key)
        expected_balance = get_expected_balance_before(
            database, hashed_acc_no, last_action.get_timestamp()
        )
        if not math.isclose(actual_balance, expected_balance):
            difference = actual_balance - expected_balance
            LOGGER.debug(
                "autocorrections: expected %r, got %r on %r [difference=%r]",
                expected_balance,
                actual_balance,
                last_action.timestamp,
                difference,
            )
            apply_autocorrections(
                database,
                acc_no,
                difference,
                mbank_anonymization_key,
                last_action,
            )


def maybe_add_negative_action(
    action: MbankAction,
    actions_per_accno: T.Dict[str, T.List[MbankAction]],
    mbank_anonymization_key: bytes,
    database: KsiemgowyDB,
    observed_acc_number: str,
) -> None:
    """Adds a transfer to the database, if it's a negative one and the account
    is observed."""
    if action.action_type != "out_transfer":
        return
    if str(action.sender_acc_no) == str(observed_acc_number):
        actions_per_accno[observed_acc_number].append(action)
        database.add_expense(action.anonymized(mbank_anonymization_key))
        LOGGER.debug("added an expense")
    else:
        LOGGER.debug("Skipping an action due to criteria not matched.")


def add_positive_action(
    action: MbankAction,
    mbank_anonymization_key: bytes,
    database: KsiemgowyDB,
    mail_config: ksiemgowy.config.MailConfig,
    should_send_mail: bool,
) -> None:
    """Adds a positive action to the base. If mail sending is enabled,
    a notification is also sent."""
    database.add_positive_transfer(action.anonymized(mbank_anonymization_key))
    LOGGER.debug("added an action")
    if not should_send_mail:
        return
    with mail_config.smtp_login() as smtp_conn:
        to_email = database.get_email_for_sender_acc_no(action.sender_acc_no)
        msg = build_confirmation_mail(
            mail_config.login,
            action,
            to_email,
        )
        smtp_conn.send_message(msg)
    LOGGER.info("sent an e-mail to %r regarding a new transfer", to_email)


def check_for_updates(
    mbank_anonymization_key: bytes,
    database: KsiemgowyDB,
    mail_config: ksiemgowy.config.MailConfig,
    observed_acc_number: str,
    should_send_mail: bool,
) -> None:
    """Checks for updates coming from the bank. If any new transfers are
    observed, they are handled according to the configuration."""
    LOGGER.info("checking for updates on %r...", mail_config.login)
    mail = mail_config.imap_connect()
    for msg in gen_unseen_mbank_emails(
        database, mail, mail_config.imap_filter
    ):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msg)
        actions_per_accno: T.Dict[str, T.List[MbankAction]] = {
            observed_acc_number: []
        }
        for action in parsed.get("actions", []):
            LOGGER.debug(
                "Observed an action: %r",
                action.anonymized(mbank_anonymization_key),
            )

            if action.action_type == "in_transfer" and str(
                action.recipient_acc_no
            ) == str(observed_acc_number):
                actions_per_accno[observed_acc_number].append(action)
                add_positive_action(
                    action,
                    mbank_anonymization_key,
                    database,
                    mail_config,
                    should_send_mail,
                )

            maybe_add_negative_action(
                action,
                actions_per_accno,
                mbank_anonymization_key,
                database,
                observed_acc_number,
            )
        maybe_apply_autocorrections(
            database, actions_per_accno, mbank_anonymization_key
        )
    LOGGER.info("check_for_updates: done")
