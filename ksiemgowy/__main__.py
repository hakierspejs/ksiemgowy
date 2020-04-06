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


def gen_unseen_mbank_emails(login, password, imap_server):
    """Connects to imap_server using login and password from the arguments,
    then yields a pair (mail_id_as_str, email_as_eml_string) for each of
    e-mails coming from mBank."""
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(login, password)
    mail.select('inbox')
    filter_s = '(SINCE "03-Mar-2020" FROM "kontakt@mbank.pl")'
    _, data = mail.search(None, filter_s)
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
            yield response_part[1].decode()
            private_state.mark_imap_id_already_handled(mail_id)


def main():
    """Program's entry point."""
    login = os.environ['IMAP_LOGIN']
    password = open('IMAP_PASSWORD').read().strip()
    public_state = ksiemgowy.public_state.PublicState()
    for msgstr in gen_unseen_mbank_emails(login, password, 'imap.gmail.com'):
        parsed = ksiemgowy.mbankmail.parse_mbank_email(msgstr)
        for action in parsed.get('actions', []):
            is_acct_watched = action.out_acc_no == '76561893'
            if action.action_type == 'in_transfer' and is_acct_watched:
                public_state.add_mbank_action(action.anonymized().asdict())


if __name__ == '__main__':
    main()
