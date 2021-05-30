#!/usr/bin/env python

"""ksiemgowy's main submodule, also used as an entry point. Contains the
logic used to generate database entries."""

# This is here because pylint has generates a false positive:
# pylint:disable=unsubscriptable-object

import atexit
import datetime
import imaplib
import os
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import time
import smtplib
import logging
import contextlib

import schedule
import yaml

import ksiemgowy.mbankmail
import ksiemgowy.public_state
import ksiemgowy.homepage_updater


IMAP_FILTER = '(SINCE "02-Apr-2020" FROM "kontakt@mbank.pl")'
LOGGER = logging.getLogger("ksiemgowy.__main__")
SEND_EMAIL = True


def imap_connect(login, password, server):
    mail = imaplib.IMAP4_SSL(server)
    mail.login(login, password)
    return mail


@contextlib.contextmanager
def smtp_login(smtplogin, smtppass):
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.ehlo()
    server.login(smtplogin, smtppass)
    yield server
    server.quit()


def send_overdue_email(server, fromaddr, overdue_email):
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
przelewom możemy zadbać o bezpieczeństwo finansowe naszej organizacji,
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


def send_confirmation_mail(
    server, fromaddr, toaddr, mbank_action, public_state
):
    msg = MIMEMultipart("alternative")
    msg["From"] = fromaddr
    emails = public_state.acc_no_to_email("arrived")
    if mbank_action.anonymized().in_acc_no in emails:
        msg["To"] = emails[mbank_action.anonymized().in_acc_no]
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
    server.send_message(msg)
    time.sleep(10)  # HACK: slow down potential self-spam


def gen_unseen_mbank_emails(db, mail):
    """Connects to imap_server using login and password from the arguments,
    then yields a pair (mail_id_as_str, email_as_eml_string) for each of
    e-mails coming from mBank."""
    mail.select("inbox")
    _, data = mail.search(None, IMAP_FILTER)
    mail_ids = data[0]
    id_list = mail_ids.split()
    for mail_id in reversed(id_list):
        _, data = mail.fetch(mail_id, "(RFC822)")
        for n, response_part in enumerate(data):
            if not isinstance(response_part, tuple):
                continue
            msg = email.message_from_string(response_part[1].decode())
            mail_key = f'{msg["Date"]}_{n}'
            if db.was_imap_id_already_handled(mail_key):
                continue
            LOGGER.info("Handling e-mail id: %r", mail_id)
            yield msg
            db.mark_imap_id_already_handled(mail_key)


def check_for_updates(  # pylint: disable=too-many-arguments
    imap_login,
    imap_password,
    imap_server,
    acc_number,
    public_db_uri,
):
    """Program's entry point."""
    LOGGER.info("checking for updates...")
    public_state = ksiemgowy.public_state.PublicState(public_db_uri)
    mail = imap_connect(imap_login, imap_password, imap_server)
    for msg in gen_unseen_mbank_emails(public_state, mail):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msg)
        for action in parsed.get("actions", []):
            LOGGER.info("Observed an action: %r", action.anonymized().asdict())
            if action.action_type == "in_transfer" and str(
                action.out_acc_no
            ) == str(acc_number):
                public_state.add_mbank_action(action.anonymized().asdict())
                if SEND_EMAIL:
                    with smtp_login(imap_login, imap_password) as server:
                        send_confirmation_mail(
                            server,
                            imap_login,
                            imap_login,
                            action,
                            public_state,
                        )
                LOGGER.info("added an action")
            elif action.action_type == "out_transfer" and str(
                action.in_acc_no
            ) == str(acc_number):
                public_state.add_expense(action.anonymized().asdict())
                LOGGER.info("added an expense")
            else:
                LOGGER.info("Skipping an action due to criteria not matched.")
    LOGGER.info("check_for_updates: done")


def build_args():
    config = yaml.load(
        open(
            os.environ.get("KSIEMGOWYD_CFG_FILE", "/etc/ksiemgowy/config.yaml")
        )
    )
    ret = []
    public_db_uri = config["PUBLIC_DB_URI"]
    for account in config["ACCOUNTS"]:
        imap_login = account["IMAP_LOGIN"]
        imap_server = account["IMAP_SERVER"]
        imap_password = account["IMAP_PASSWORD"]
        acc_no = account["ACC_NO"]
        ret.append(
            [
                imap_login,
                imap_password,
                imap_server,
                acc_no,
                public_db_uri,
            ]
        )
    return ret


@atexit.register
def atexit_handler(*_, **__):
    LOGGER.info("Shutting down")


def notify_about_overdues(
    imap_login, imap_password, _imap_server, public_db_uri
):
    LOGGER.info("notify_about_overdues()")
    public_state = ksiemgowy.public_state.PublicState(public_db_uri)
    d = {}
    for x in public_state.list_mbank_actions():
        if x.in_acc_no not in d or d[x.in_acc_no].timestamp < x.timestamp:
            d[x.in_acc_no] = x

    ago_35d = datetime.datetime.now() - datetime.timedelta(days=35)
    ago_55d = datetime.datetime.now() - datetime.timedelta(days=55)
    overdues = []
    emails = public_state.acc_no_to_email("overdue")
    for k in d:
        if ago_55d < d[k].timestamp < ago_35d:
            if d[k].in_acc_no in emails:
                overdues.append(emails[d[k].in_acc_no])

    if SEND_EMAIL:
        with smtp_login(imap_login, imap_password) as server:
            for overdue in overdues:
                send_overdue_email(server, imap_login, overdue)

    LOGGER.info("done notify_about_overdues()")


def main():
    logging.basicConfig(level="INFO")
    LOGGER.info("ksiemgowyd started")
    args = build_args()
    public_db_uri = args[0][-1]
    public_state = ksiemgowy.public_state.PublicState(public_db_uri)
    emails = public_state.acc_no_to_email(  # pylint: disable=unused-variable
        "arrived"
    )  # noqa
    # the weird schedule is supposed to try to accomodate different lifestyles
    for account in args:
        check_for_updates(*account)
        schedule.every().hour.do(check_for_updates, *account)

    # use the last specified account for overdue notifications:
    schedule.every((24 * 3) + 5).hours.do(notify_about_overdues, *args[-1])

    deploy_key_path = os.environ["DEPLOY_KEY_PATH"]
    public_db_uri = args[0][-2]
    public_state = ksiemgowy.public_state.PublicState(public_db_uri)
    schedule.every().hour.do(
        ksiemgowy.homepage_updater.maybe_update, public_state, deploy_key_path
    )
    ksiemgowy.homepage_updater.maybe_update(public_state, deploy_key_path)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
