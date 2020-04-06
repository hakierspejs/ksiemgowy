#!/usr/bin/env pyhon

"""Parsuje mail z mBanku, podając info o przelewach przychodzących jako
JSON."""

import re
import json
import argparse
import email
import dataclasses
import os
import copy
import hashlib

import lxml.html

INCOMING_RE = re.compile(
    '^mBank: Przelew przych. z rach. (?P<in_acc_no>\\d{4}\\.{3}\\d{6})'
    ' na rach\\. (?P<out_acc_no>\\d{8}) '
    'kwota (?P<amount_pln>\\d+,\\d{2}) PLN od (?P<in_person>.+); '
    '(?P<in_desc>.+); Dost\\. (?P<balance>\\d+,\\d{2}) PLN$'
)


MBANK_ANONYMIZATION_KEY = os.environ['MBANK_ANONYMIZATION_KEY'].encode()


def anonymize(s):
    return hashlib.sha256(s.encode() + MBANK_ANONYMIZATION_KEY).hexdigest()


@dataclasses.dataclass
class MbankAction:
    in_acc_no: str
    out_acc_no: str
    amount_pln: str
    in_person: str
    in_desc: str
    balance: str
    timestamp: str
    action_type: str

    def anonymized(self):
        new = copy.copy(self)
        new.in_acc_no = anonymize(self.in_acc_no)
        new.in_person = anonymize(self.in_person)
        new.in_desc = anonymize(self.in_desc)
        return new

    asdict = dataclasses.asdict


def parse_mbank_html(mbank_html):
    """Parses mBank .htm attachment file and generates a list of actions
    that were derived from it."""
    h = lxml.html.fromstring(mbank_html)
    date = h.xpath('//h5/text()')[0].split(' - ')[0]
    actions = []
    for row in h.xpath('//tr')[2:]:
        desc_e = row.xpath('.//td[2]/text()')
        if not desc_e:
            continue
        desc_s = desc_e[0].strip()
        time = row.xpath('.//td[1]')[0].text_content().strip()
        g = INCOMING_RE.match(desc_s)
        if not g:
            continue
        action = g.groupdict()
        action['action_type'] = 'in_transfer'
        action['timestamp'] = f'{date} {time}'
        actions.append(MbankAction(**action))
    return {'actions': actions}


def parse_mbank_email(msgstr):
    """Finds attachment with mBank account update in an .eml mBank email,
    then behaves like parse_mbank_html."""
    msg = email.message_from_string(msgstr)
    parsed = {}
    for part in msg.walk():
        params = dict(part.get_params())
        if 'name' not in params or part.get_content_type() != 'text/html':
            continue
        parsed = parse_mbank_html(part.get_payload(decode=True))
        if parsed['actions']:
            break
    return parsed


def parse_args():
    """Parses command-line arguments and returns them in a form usable as
    **kwargs."""
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('-i', '--input-fpath', required=True)
    parser.add_argument('--mode', choices=['eml', 'html'], required=True)
    return parser.parse_args().__dict__


def main(input_fpath, mode):
    """Entry point for the submodule, used for diagnostics. Reads data from
    input_fpath, then runs either parse_mbank_html or parse_mbank_email,
    depending on the mode."""
    with open(input_fpath) as f:
        s = f.read()
    if mode == 'html':
        result = parse_mbank_html(s)
    elif mode == 'eml':
        result = parse_mbank_email(s)
    else:
        raise RuntimeError('Unexpected mode: %s' % mode)
    print(json.dumps(result))


if __name__ == '__main__':
    main(**parse_args())
