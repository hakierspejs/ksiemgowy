#!/usr/bin/env python

"""ksiemgowy's main submodule, also used as an entry point. Contains the
logic used to generate database entries."""


import atexit
import datetime
import imaplib
import os
import email
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass
import typing as T
from typing import Any, Dict, Iterator


import time
import smtplib
import logging
import contextlib

import yaml

import schedule as schedule_module  # type: ignore

import ksiemgowy.mbankmail
import ksiemgowy.models
import ksiemgowy.homepage_updater

# those are for type annotations:
from ksiemgowy.mbankmail import MbankAction
from ksiemgowy.models import KsiemgowyDB


IMAP_FILTER = '(SINCE "02-Apr-2020" FROM "kontakt@mbank.pl")'
LOGGER = logging.getLogger("ksiemgowy.__main__")
SEND_EMAIL = True


@dataclass(frozen=True)
class MailConfig:
    """A structure that stores our mail credentials and exposes an interface
    that allows the user to create SMTP and IMAP connections. Tested with
    GMail."""

    login: str
    password: str
    server: str

    def imap_connect(self) -> imaplib.IMAP4_SSL:
        """Logs in to IMAP using given credentials."""
        mail = imaplib.IMAP4_SSL(self.server)
        mail.login(self.login, self.password)
        return mail

    @contextlib.contextmanager
    def smtp_login(self) -> T.Generator[smtplib.SMTP_SSL, None, None]:
        """A context manager that handles SMTP login and logout."""
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.ehlo()
        server.login(self.login, self.password)
        yield server
        server.quit()


@dataclass(frozen=True)
class KsiemgowyAccount:
    """Stores information tied to a specific bank account: its number and
    an e-mail configuration used to handle communications related to it."""

    acc_number: str
    mail_config: MailConfig


@dataclass(frozen=True)
class KsiemgowyConfig:
    """Stores information required to start Ksiemgowy. This includes
    database, e-mail and website credentials, as well as cryptographic pepper
    used to anonymize account data."""

    database_uri: str
    deploy_key_path: str
    accounts: T.List[KsiemgowyAccount]
    mbank_anonymization_key: bytes

    def get_account_for_overdue_notifications(self) -> KsiemgowyAccount:
        """Returns an e-mail account used for overdue notifications. Currently
        it's the last one mentioned in the configuration."""
        return self.accounts[-1]


def send_overdue_email(
    server: smtplib.SMTP_SSL, fromaddr: str, overdue_email: str
) -> None:
    """Sends an e-mail notifying that a member is overdue with their
    payments."""
    msg = MIMEMultipart("alternative")
    msg["From"] = fromaddr
    msg["To"] = overdue_email
    msg["Bcc"] = fromaddr
    msg["Subject"] = "Hej, wszystko ok?"

    message_text = """Hej,

Piszę do Ciebie, gdyż minęło ponad 35 dni od Twojej ostatniej składki
na rzecz Hakierspejsu. Między innymi stąd też moje pytanie: cześć,
żyjesz? :) Czy wszystko jest OK? Jeśli tak, przelej proszę składkę - albo
najlepiej, ustaw comiesięczne zlecenie stałe:

Numer konta: 56 1140 2004 0000 3902 8108 9394

Zalecana składka: 100 zł

Tytuł: darowizna na cele statutowe

(jeżeli jesteś członkiem Hakierspejsu, w tytule napisz zamiast tego "składka
członkowska - 1mies - pełna miesięczna" oraz Twój nick lub imię i nazwisko)

Mam nadzieję, że udział w Hakierspejsie dalej Cię interesuje. Daj
proszę znać, jeżeli masz jakiekolwiek pytania lub sugestie.

Niezależnie od tego czy uda Ci się przelać kolejną składkę - dziękuję
za Twój dotychczasowy wkład w działalność HSŁ! Dzięki regularnym
przelewom możemy zadatabaseać o bezpieczeństwo finansowe naszej organizacji,
w szczególności regularne opłacanie czynszu oraz gromadzenie środków
na dalszy rozwój :)

Miłego dnia,
d33tah

PS. Wiadomość wysłana jest automatycznie co kilka dni przez program
"ksiemgowy". Więcej szczegółów tutaj:

https://github.com/hakierspejs/wiki/wiki/Finanse#przypomnienie-o-sk%C5%82adkach
"""

    msg.attach(MIMEText(message_text, "plain", "utf-8"))
    server.send_message(msg)
    time.sleep(10)  # HACK: slow down potential self-spam


def build_confirmation_mail(
    mbank_anonymization_key: bytes,
    fromaddr: str,
    toaddr: str,
    mbank_action: MbankAction,
    emails: Dict[str, str],
) -> MIMEMultipart:
    """Sends an e-mail confirming that a membership due has arrived and was
    accounted for."""
    msg = MIMEMultipart("alternative")
    msg["From"] = fromaddr
    acc_no = mbank_action.anonymized(mbank_anonymization_key).in_acc_no
    if acc_no in emails:
        msg["To"] = emails[acc_no]
        msg["Cc"] = toaddr
    else:
        msg["To"] = toaddr
    msg["Subject"] = "ksiemgowyd: zaksiemgowano przelew! :)"
    message_text = f"""Dziękuję za wspieranie Hakierspejsu! ❤

Twój przelew na kwotę {mbank_action.amount_pln} zł z dnia \
{mbank_action.timestamp} został pomyślnie zaksięgowany przez Ksiemgowego. \
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
    database: KsiemgowyDB, mail: imaplib.IMAP4_SSL
) -> Iterator[Message]:
    """Connects to imap_server using login and password from the arguments,
    then yields a pair (mail_id_as_str, email_as_eml_string) for each of
    e-mails coming from mBank."""
    mail.select("inbox")
    _, data = mail.search(None, IMAP_FILTER)
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


def check_for_updates(  # pylint: disable=too-many-arguments
    mbank_anonymization_key: bytes,
    database: KsiemgowyDB,
    mail_config: MailConfig,
    acc_number: str,
) -> None:
    """Program's entry point."""
    LOGGER.info("checking for updates...")
    mail = mail_config.imap_connect()
    for msg in gen_unseen_mbank_emails(database, mail):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msg)
        for action in parsed.get("actions", []):
            LOGGER.info(
                "Observed an action: %r",
                action.anonymized(mbank_anonymization_key),
            )
            if action.action_type == "in_transfer" and str(
                action.out_acc_no
            ) == str(acc_number):
                database.add_positive_transfer(
                    action.anonymized(mbank_anonymization_key)
                )
                if SEND_EMAIL:
                    with mail_config.smtp_login() as smtp_conn:
                        emails = database.acc_no_to_email("arrived")
                        msg = build_confirmation_mail(
                            mbank_anonymization_key,
                            mail_config.login,
                            mail_config.login,
                            action,
                            emails,
                        )
                        smtp_conn.send_message(msg)
                        time.sleep(10)  # HACK: slow down potential self-spam

                LOGGER.info("added an action")
            elif action.action_type == "out_transfer" and str(
                action.in_acc_no
            ) == str(acc_number):
                database.add_expense(
                    action.anonymized(mbank_anonymization_key)
                )
                LOGGER.info("added an expense")
            else:
                LOGGER.info("Skipping an action due to criteria not matched.")
    LOGGER.info("check_for_updates: done")


@atexit.register
def atexit_handler(*_: T.Any, **__: T.Any) -> None:
    """Handles program termination in a predictable way."""
    LOGGER.info("Shutting down")


def notify_about_overdues(
    database: KsiemgowyDB,
    mail_config: MailConfig,
) -> None:
    """Checks whether any of the organization members is overdue and notifies
    them about that fact."""
    LOGGER.info("notify_about_overdues()")
    latest_dues: T.Dict[str, MbankAction] = {}
    for action in database.list_positive_transfers():
        if (
            action.in_acc_no not in latest_dues
            or latest_dues[action.in_acc_no].get_timestamp()
            < action.get_timestamp()
        ):
            latest_dues[action.in_acc_no] = action

    ago_35d = datetime.datetime.now() - datetime.timedelta(days=35)
    ago_55d = datetime.datetime.now() - datetime.timedelta(days=55)
    overdues = []
    emails = database.acc_no_to_email("overdue")
    for payment in latest_dues.values():
        if ago_55d < payment.get_timestamp() < ago_35d:
            if payment.in_acc_no in emails:
                overdues.append(emails[payment.in_acc_no])

    if SEND_EMAIL:
        with mail_config.smtp_login() as server:
            for overdue in overdues:
                send_overdue_email(server, mail_config.login, overdue)

    LOGGER.info("done notify_about_overdues()")


def load_config(
    config_file: T.IO[T.Any], env: T.Dict[str, str]
) -> KsiemgowyConfig:
    """Parses the configuration file and builds arguments for all routines."""
    mbank_anonymization_key = env["MBANK_ANONYMIZATION_KEY"].encode()
    config = yaml.load(config_file)
    accounts = []
    database_uri = config["PUBLIC_DB_URI"]
    deploy_key_path = env["DEPLOY_KEY_PATH"]
    for account in config["ACCOUNTS"]:
        imap_login = account["IMAP_LOGIN"]
        imap_server = account["IMAP_SERVER"]
        imap_password = account["IMAP_PASSWORD"]
        acc_no = account["ACC_NO"]
        accounts.append(
            KsiemgowyAccount(
                acc_number=acc_no,
                mail_config=MailConfig(
                    login=imap_login,
                    password=imap_password,
                    server=imap_server,
                ),
            )
        )

    return KsiemgowyConfig(
        database_uri=database_uri,
        accounts=accounts,
        mbank_anonymization_key=mbank_anonymization_key,
        deploy_key_path=deploy_key_path,
    )


def every_seconds_do(
    num_seconds: int,
    called_fn: T.Callable[..., Any],
    args: T.Any,
    kwargs: T.Any,
) -> None:
    """A wrapper for "schedule" module. Intended to satisfy MyPy, as well as
    increasing testability by not relying on global state."""

    schedule_module.every(num_seconds).seconds.do(called_fn, *args, **kwargs)


def main_loop() -> None:
    """Main loop. Factored out for increased testability."""
    while True:
        schedule_module.run_pending()
        time.sleep(1)


def main(
    config: KsiemgowyConfig,
    database: ksiemgowy.models.KsiemgowyDB,
    homepage_update: T.Callable[[ksiemgowy.models.KsiemgowyDB, str], None],
    register_fn: T.Callable[[int, T.Callable[..., Any], T.Any, T.Any], None],
    main_loop_fn: T.Callable[[], None],
) -> None:
    """Program's entry point. Schedules periodic execution of all routines."""
    logging.basicConfig(level="INFO")
    LOGGER.info("ksiemgowyd started")

    # pylint:disable=unused-variable
    emails = database.acc_no_to_email("arrived")  # noqa
    for account in config.accounts:
        args = account.__dict__
        args["mbank_anonymization_key"] = config.mbank_anonymization_key
        args["database"] = database
        check_for_updates(
            config.mbank_anonymization_key,
            database,
            account.mail_config,
            account.acc_number,
        )

        register_fn(
            3600,
            check_for_updates,
            [
                config.mbank_anonymization_key,
                database,
                account.mail_config,
                account.acc_number,
            ],
            {},
        )

    # the weird schedule is supposed to try to accomodate different lifestyles
    # use the last specified account for overdue notifications:
    overdue_account = config.get_account_for_overdue_notifications()
    register_fn(
        (3600 * ((24 * 3) + 5)),
        notify_about_overdues,
        [
            database,
            overdue_account.mail_config,
        ],
        {},
    )

    register_fn(3600, homepage_update, [database, config.deploy_key_path], {})
    homepage_update(database, config.deploy_key_path)

    main_loop_fn()


def entrypoint() -> None:
    """Program's entry point. Loads config, instantiates required objects
    and then runs the main function."""
    with open(
        os.environ.get("KSIEMGOWYD_CFG_FILE", "/etc/ksiemgowy/config.yaml"),
        encoding="utf8",
    ) as config_file:
        config = load_config(config_file, dict(os.environ))
    main(
        config,
        ksiemgowy.models.KsiemgowyDB(config.database_uri),
        ksiemgowy.homepage_updater.maybe_update,
        every_seconds_do,
        main_loop,
    )


if __name__ == "__main__":
    entrypoint()
