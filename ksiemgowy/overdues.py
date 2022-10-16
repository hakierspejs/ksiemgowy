"""Handles the task of sending notifications to users when they are overdue."""

import datetime
import logging
import typing as T
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import ksiemgowy.config
from ksiemgowy.mbankmail import MbankAction
from ksiemgowy.models import KsiemgowyDB


LOGGER = logging.getLogger("ksiemgowy.__main__")


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
członkowska - 1 mies. - pełna miesięczna" oraz Twój nick lub imię i nazwisko)

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


def notify_about_overdues(
    database: KsiemgowyDB,
    mail_config: ksiemgowy.config.MailConfig,
) -> None:
    """Checks whether any of the organization members is overdue and notifies
    them about that fact."""
    LOGGER.info("notify_about_overdues()")
    latest_dues: T.Dict[str, MbankAction] = {}
    for action in database.list_positive_transfers():
        if (
            action.sender_acc_no not in latest_dues
            or latest_dues[action.sender_acc_no].get_timestamp()
            < action.get_timestamp()
        ):
            latest_dues[action.sender_acc_no] = action

    now = datetime.datetime.now()
    ago_35d = now - datetime.timedelta(days=35)
    ago_55d = now - datetime.timedelta(days=55)
    overdues = []
    emails = database.get_potentially_overdue_accounts(now)
    for payment in latest_dues.values():
        if ago_55d < payment.get_timestamp() < ago_35d:
            if payment.sender_acc_no in emails:
                overdues.append(payment.sender_acc_no)

    with mail_config.smtp_login() as server:
        for sender_acc_no in overdues:
            email = emails[sender_acc_no]
            send_overdue_email(server, mail_config.login, email)
            database.postpone_next_notification(sender_acc_no, now)

    LOGGER.info("done notify_about_overdues()")
