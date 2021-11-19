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

import ksiemgowy.config
from ksiemgowy.mbankmail import MbankAction, anonymize
from ksiemgowy.models import KsiemgowyDB


LOGGER = logging.getLogger("ksiemgowy.__main__")


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
            LOGGER.info("Handling e-mail id: %r", mail_id)
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
    if difference < 0:

        action = MbankAction(
            recipient_acc_no="AUTOCORRECTION",
            sender_acc_no=acc_no,
            amount_pln=-difference,
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
            sender_acc_no="AUTOCORRECTION",
            recipient_acc_no=acc_no,
            amount_pln=difference,
            in_person="AUTOCORRECTION",
            in_desc="AUTOCORRECTION",
            balance=last_action.balance,
            timestamp=last_action.timestamp,
            action_type="out_transfer",
        )
        database.add_expense(action.anonymized(mbank_anonymization_key))

    LOGGER.info("*** apply_autocorrections: action=%r", action)


def get_expected_balance_before(
    database: KsiemgowyDB, acc_no: str, before: datetime.datetime
) -> float:
    """Calculates expected balance for a given account, as of given date. Bases
    the calculations on data stored in the database."""
    balance_so_far = 0.0
    for action in database.list_expenses():
        if action.recipient_acc_no != acc_no:
            continue
        if action.get_timestamp() > before:
            continue
        balance_so_far += action.amount_pln

    for action in database.list_positive_transfers():
        if action.sender_acc_no != acc_no:
            continue
        if action.get_timestamp() > before:
            continue
        balance_so_far += action.amount_pln

    return balance_so_far


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
        actual_balance = last_action.balance
        LOGGER.info(
            "maybe_apply_autocorrections: "
            "last_action.balance=%r, actual_balance=%r",
            last_action.balance,
            actual_balance,
        )
        hashed_acc_no = anonymize(acc_no, mbank_anonymization_key)
        expected_balance = get_expected_balance_before(
            database, hashed_acc_no, last_action.get_timestamp()
        )
        if not math.isclose(actual_balance, expected_balance):
            difference = actual_balance - expected_balance
            LOGGER.info(
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
    if action.action_type == "out_transfer" and str(
        action.recipient_acc_no
    ) == str(observed_acc_number):
        actions_per_accno[observed_acc_number].append(action)
        database.add_expense(action.anonymized(mbank_anonymization_key))
        LOGGER.info("added an expense")
    else:
        LOGGER.info("Skipping an action due to criteria not matched.")


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
    LOGGER.info("added an action")
    if not should_send_mail:
        return
    with mail_config.smtp_login() as smtp_conn:
        to_email = database.get_email_for_recipient_acc_no(
            action.recipient_acc_no
        )
        msg = build_confirmation_mail(
            mail_config.login,
            action,
            to_email,
        )
        smtp_conn.send_message(msg)
    LOGGER.info("sent an e-mail")


def check_for_updates(
    mbank_anonymization_key: bytes,
    database: KsiemgowyDB,
    mail_config: ksiemgowy.config.MailConfig,
    observed_acc_number: str,
    should_send_mail: bool,
) -> None:
    """Checks for updates coming from the bank. If any new transfers are
    observed, they are handled according to the configuration."""
    LOGGER.info("checking for updates...")
    mail = mail_config.imap_connect()
    for msg in gen_unseen_mbank_emails(
        database, mail, mail_config.imap_filter
    ):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msg)
        actions_per_accno: T.Dict[str, T.List[MbankAction]] = {
            observed_acc_number: []
        }
        for action in parsed.get("actions", []):
            LOGGER.info(
                "Observed an action: %r",
                action.anonymized(mbank_anonymization_key),
            )

            if action.action_type == "in_transfer" and str(
                action.sender_acc_no
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
