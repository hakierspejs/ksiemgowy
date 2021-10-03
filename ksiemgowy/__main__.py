#!/usr/bin/env python

"""ksiemgowy's main submodule, also used as an entry point. Contains the
logic used to generate database entries."""


import atexit
import datetime
import imaplib
import os
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass
import typing as T


import time
import smtplib
import logging
import contextlib

import schedule as schedule_module
import yaml

import ksiemgowy.mbankmail
import ksiemgowy.models
import ksiemgowy.homepage_updater


IMAP_FILTER = '(SINCE "02-Apr-2020" FROM "kontakt@mbank.pl")'
LOGGER = logging.getLogger("ksiemgowy.__main__")
SEND_EMAIL = True


@dataclass(frozen=True)
class MailConfig:
    login: str
    password: str
    server: str

    def imap_connect(self):
        """Logs in to IMAP using given credentials."""
        mail = imaplib.IMAP4_SSL(self.server)
        mail.login(self.login, self.password)
        return mail

    @contextlib.contextmanager
    def smtp_login(self):
        """A context manager that handles SMTP login and logout."""
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.ehlo()
        server.login(self.login, self.password)
        yield server
        server.quit()


@dataclass(frozen=True)
class KsiemgowyAccount:
    acc_number: str
    mail_config: MailConfig


@dataclass(frozen=True)
class KsiemgowyConfig:
    database_uri: str
    deploy_key_path: str
    accounts: T.List[KsiemgowyAccount]
    mbank_anonymization_key: str

    def get_account_for_overdue_notifications(self):
        return self.accounts[-1]


def send_overdue_email(server, fromaddr, overdue_email):
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
    mbank_anonymization_key,
    fromaddr,
    toaddr,
    mbank_action,
    emails,
):
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


def gen_unseen_mbank_emails(database, mail):
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
    mbank_anonymization_key,
    database,
    mail_config,
    acc_number,
):
    """Program's entry point."""
    LOGGER.info("checking for updates...")
    mail = mail_config.imap_connect()
    for msg in gen_unseen_mbank_emails(database, mail):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msg)
        for action in parsed.get("actions", []):
            LOGGER.info(
                "Observed an action: %r",
                action.anonymized(mbank_anonymization_key).asdict(),
            )
            if action.action_type == "in_transfer" and str(
                action.out_acc_no
            ) == str(acc_number):
                database.add_positive_transfer(
                    action.anonymized(mbank_anonymization_key).asdict()
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
                    action.anonymized(mbank_anonymization_key).asdict()
                )
                LOGGER.info("added an expense")
            else:
                LOGGER.info("Skipping an action due to criteria not matched.")
    LOGGER.info("check_for_updates: done")


@atexit.register
def atexit_handler(*_, **__):
    """Handles program termination in a predictable way."""
    LOGGER.info("Shutting down")


def notify_about_overdues(
    database,
    mail_config,
):
    """Checks whether any of the organization members is overdue and notifies
    them about that fact."""
    LOGGER.info("notify_about_overdues()")
    latest_dues = {}
    for action in database.list_positive_transfers():
        if (
            action.in_acc_no not in latest_dues
            or latest_dues[action.in_acc_no].timestamp < action.timestamp
        ):
            latest_dues[action.in_acc_no] = action

    ago_35d = datetime.datetime.now() - datetime.timedelta(days=35)
    ago_55d = datetime.datetime.now() - datetime.timedelta(days=55)
    overdues = []
    emails = database.acc_no_to_email("overdue")
    for payment in latest_dues.values():
        if ago_55d < payment.timestamp < ago_35d:
            if payment.in_acc_no in emails:
                overdues.append(emails[payment.in_acc_no])

    if SEND_EMAIL:
        with mail_config.smtp_login() as server:
            for overdue in overdues:
                send_overdue_email(server, mail_config.login, overdue)

    LOGGER.info("done notify_about_overdues()")


def load_config(config_file, env):
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
            [
                imap_login,
                imap_password,
                imap_server,
                acc_no,
            ]
        )

    return KsiemgowyConfig(database_uri=database_uri, accounts=accounts,
                           mbank_anonymization_key=mbank_anonymization_key,
                           deploy_key_path=deploy_key_path)


def get_database(config):
    database_uri = config.accounts[0][-1]
    return ksiemgowy.models.KsiemgowyDB(database_uri)


def main(config, database, homepage_update, schedule, should_keep_running):
    """Program's entry point. Schedules periodic execution of all routines."""
    logging.basicConfig(level="INFO")
    LOGGER.info("ksiemgowyd started")

    # pylint:disable=unused-variable
    emails = database.acc_no_to_email("arrived")  # noqa
    for account in config.accounts:
        args = account.__dict__
        args['mbank_anonymization_key'] = config.mbank_anonymization_key
        args['database'] = database
        check_for_updates(**args)
        schedule.every().hour.do(check_for_updates, **args)

    # the weird schedule is supposed to try to accomodate different lifestyles
    # use the last specified account for overdue notifications:
    overdue_account = config.get_account_for_overdue_notifications()
    overdue_args = {'database':  database,
                    "mail_config": overdue_account.mail_config}
    schedule.every((24 * 3) + 5).hours.do(notify_about_overdues,
                                          **overdue_args)

    schedule.every().hour.do(
        homepage_update, database, config.deploy_key_path
    )
    homepage_update(database, config.deploy_key_path)

    while should_keep_running():
        schedule.run_pending()
        time.sleep(1)


def entrypoint():
    with open(
        os.environ.get("KSIEMGOWYD_CFG_FILE", "/etc/ksiemgowy/config.yaml"),
        encoding="utf8",
    ) as config_file:
        config = load_config(config_file, os.environ)
    database = get_database(config)
    main(config, database, ksiemgowy.homepage_updater.maybe_update,
         schedule_module, lambda: True)


if __name__ == "__main__":
    entrypoint()
