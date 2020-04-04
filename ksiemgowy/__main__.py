#!/usr/bin/env python

"""ksiemgowy's main submodule, also used as an entry point. Contains the
logic used to generate database entries."""

# This is here because pylint has generates a false positive:
# pylint:disable=unsubscriptable-object

import imaplib
import os

import ksiemgowy.mbankmail
import ksiemgowy.private_state
import ksiemgowy.public_state


def gen_mbank_emails(login, password, imap_server):
    """Connects to imap_server using login and password from the arguments,
    then yields a pair (mail_id_as_str, email_as_eml_string) for each of
    e-mails coming from mBank."""
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(login, password)
    mail.select('inbox')
    _, data = mail.search(None, 'FROM', 'kontakt@mbank.pl')
    mail_ids = data[0]
    id_list = mail_ids.split()
    private_state = ksiemgowy.private_state.PrivateState()
    for mail_id in reversed(id_list):
        if private_state.was_imap_id_already_handled(mail_id):
            continue
        _, data = mail.fetch(mail_id, '(RFC822)')
        for response_part in data:
            if not isinstance(response_part, tuple):
                continue
            yield mail_id.decode(), response_part[1].decode()
            private_state.mark_imap_id_already_handled(mail_id)


def main():
    """Program's entry point."""
    login = os.environ['IMAP_LOGIN']
    password = open('IMAP_PASSWORD').read().strip()
    public_state = ksiemgowy.public_state.PublicState()
    for mail_id, msgstr in gen_mbank_emails(login, password, 'imap.gmail.com'):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msgstr)
        for action in parsed.get('actions', []):
            is_acct_watched = action['in_acc_no'] == '9811...178886'
            if action['type'] == 'in_transfer' and is_acct_watched:
                public_state.add_mbank_action(action)


if __name__ == '__main__':
    main()
