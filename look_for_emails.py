#!/usr/bin/env python

import imaplib
import os
import collections

import mbankmail


def gen_mbank_emails(login, password, imap_server):
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(login, password)
    mail.select('inbox')
    _, data = mail.search(None, 'FROM', 'kontakt@mbank.pl')
    mail_ids = data[0]
    id_list = mail_ids.split()
    for mail_id in reversed(id_list):
        _, data = mail.fetch(mail_id, '(RFC822)')
        for response_part in data:
            if not isinstance(response_part, tuple):
                continue
            yield mail_id.decode(), response_part[1].decode()


def main():
    actions = collections.defaultdict(list)
    login = os.environ['IMAP_LOGIN']
    password = open('IMAP_PASSWORD').read().strip()
    for mail_id, msgstr in gen_mbank_emails(login, password, 'imap.gmail.com'):
        parsed = mbankmail.parse_mbank_email(msgstr)
        for action in parsed.get('actions', []):
            is_acct_watched = action['in_acc_no'] == '9811...178886'
            if action['type'] == 'in_transfer' and is_acct_watched:
                actions[mail_id].append(action)

    import json
    print(json.dumps(actions))


if __name__ == '__main__':
    main()
