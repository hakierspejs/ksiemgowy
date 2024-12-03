"""Handles the task of finding out about new wire transfers and notifying the
users once they're observed."""

import typing as T
import logging
import imaplib
import email
from email.message import Message
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import ksiemgowy.config
from ksiemgowy.mbankmail import MbankAction
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
    for mail_id in reversed(id_list):
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


def check_for_updates(
    mbank_anonymization_key: bytes,
    database: KsiemgowyDB,
    mail_config: ksiemgowy.config.MailConfig,
    acc_number: str,
    should_send_mail: bool,
) -> None:
    """Program's entry point."""
    LOGGER.info("checking for updates...")
    mail = mail_config.imap_connect()
    for msg in gen_unseen_mbank_emails(
        database, mail, mail_config.imap_filter
    ):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msg)
        for action in parsed.get("actions", []):
            LOGGER.info(
                "Observed an action: %r",
                action.anonymized(mbank_anonymization_key),
            )
            if action.action_type == "in_transfer" and str(
                action.recipient_acc_no
            ) == str(acc_number):
                database.add_positive_transfer(
                    action.anonymized(mbank_anonymization_key)
                )
                if should_send_mail:
                    with mail_config.smtp_login() as smtp_conn:
                        to_email = database.get_email_for_sender_acc_no(
                            action.sender_acc_no
                        )
                        msg = build_confirmation_mail(
                            mail_config.login,
                            action,
                            to_email,
                        )
                        smtp_conn.send_message(msg)

                LOGGER.info("added an action")
            elif action.action_type == "out_transfer" and str(
                action.sender_acc_no
            ) == str(acc_number):
                database.add_expense(
                    action.anonymized(mbank_anonymization_key)
                )
                LOGGER.info("added an expense")
            else:
                LOGGER.info("Skipping an action due to criteria not matched.")
    LOGGER.info("check_for_updates: done")
