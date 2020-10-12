#!/usr/bin/env python

"""ksiemgowy's main submodule, also used as an entry point. Contains the
logic used to generate database entries."""

# This is here because pylint has generates a false positive:
# pylint:disable=unsubscriptable-object

import atexit
import imaplib
import os
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import time
import smtplib
import logging

import schedule

import ksiemgowy.mbankmail
import ksiemgowy.private_state
import ksiemgowy.public_state


IMAP_FILTER = '(SINCE "02-Apr-2020" FROM "kontakt@mbank.pl")'
ACC_NO = "76561893"
LOGGER = logging.getLogger("ksiemgowy.__main__")


def imap_connect(login, password, server):
    mail = imaplib.IMAP4_SSL(server)
    mail.login(login, password)
    return mail


def smtp_login(smtplogin, smtppass):
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.ehlo()
    server.login(smtplogin, smtppass)
    return server


def send_mail(server, fromaddr, toaddr, payload):
    msg = "From: %s\r\nTo: %s\r\n\r\n%s" % (fromaddr, toaddr, payload)

    server.set_debuglevel(1)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = u'ksiemgowyd: update'
    part1 = MIMEText(payload, "plain", "utf-8")
    msg.attach(part1)
    server.sendmail(fromaddr, toaddr, msg.as_string().encode('ascii'))
    server.quit()
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
            LOGGER.info("Handling e-mail id: %r", mail_id)
            yield msg
        if db.was_imap_id_already_handled(mail_key):
            continue
        db.mark_imap_id_already_handled(mail_key)


def check_for_updates(
    imap_login, imap_password, imap_server, public_db_uri, private_db_uri
):
    """Program's entry point."""
    LOGGER.info("check_for_updates()")
    public_state = ksiemgowy.public_state.PublicState(public_db_uri)
    private_state = ksiemgowy.private_state.PrivateState(private_db_uri)
    mail = imap_connect(imap_login, imap_password, imap_server)
    for msg in gen_unseen_mbank_emails(private_state, mail):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msg)
        for action in parsed.get("actions", []):
            LOGGER.info("Observed an action: %r", action.anonymized().asdict())
            is_acct_watched = action.out_acc_no == ACC_NO
            if action.action_type == "in_transfer" and is_acct_watched:
                public_state.add_mbank_action(action.anonymized().asdict())
                server = smtp_login(imap_login, imap_password)
                send_mail(server, imap_login, imap_login, str(action))
                LOGGER.info("added an action")
    LOGGER.info("check_for_updates: done")


def build_args():
    public_db_uri = os.environ["PUBLIC_DB_URI"]
    private_db_uri = os.environ["PRIVATE_DB_URI"]
    imap_login = os.environ["IMAP_LOGIN"]
    imap_server = os.environ["IMAP_SERVER"]
    imap_password_path = os.environ["IMAP_PASSWORD_PATH"]
    imap_password = open(imap_password_path).read().strip()
    return (imap_login, imap_password, imap_server, public_db_uri, private_db_uri)


@atexit.register
def atexit_handler(*_, **__):
    LOGGER.info("Shutting down")


def main():
    logging.basicConfig(level="INFO")
    LOGGER.info("ksiemgowyd started")
    args = build_args()
    check_for_updates(*args)
    schedule.every().hour.do(check_for_updates, *args)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
