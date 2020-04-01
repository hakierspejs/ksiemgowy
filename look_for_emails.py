#!/usr/bin/env python

import imaplib
import email
import os

import mbankmail

mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login(os.environ['GMAIL_EMAIL'], open('GMAIL_PASSWORD').read().strip())
mail.select('inbox')
_, data = mail.search(None, 'FROM', 'kontakt@mbank.pl')
mail_ids = data[0]
id_list = mail_ids.split()

actions = {}
for mail_id in reversed(id_list):
    _, data = mail.fetch(mail_id, '(RFC822)')
    for response_part in data:
        if not isinstance(response_part, tuple):
            continue
        msg = email.message_from_string(response_part[1].decode())
        done = False
        for part in msg.walk():
            params = dict(part.get_params())
            if 'name' not in params or part.get_content_type() != 'text/html':
                continue
            parsed = mbankmail.parse_mbank_html(part.get_payload(decode=True))
            if not parsed['actions']:
                continue
            actions[mail_id.decode()] = parsed

import json
print(json.dumps(actions))
