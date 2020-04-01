#!/usr/bin/env pyhon

"""Parsuje mail z mBanku, podając info o przelewach przychodzących jako
JSON."""

import re
import json
import argparse
import lxml.html

INCOMING_RE = re.compile(
    '^mBank: Przelew przych. z rach. (?P<in_acc_no>\\d{4}\\.{3}\\d{6})'
    ' na rach\\. (?P<out_acc_no>\\d{8}) '
    'kwota (?P<amount_pln>\\d+,\\d{2}) PLN od (?P<in_person>.+) U; '
    '(?P<in_desc>.+); Dost\\. (?P<balance>\\d+,\\d{2}) PLN$'
)


def parse_args():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('-i', '--input-fpath', required=True)
    return parser.parse_args().__dict__


def parse_mbank_html(mbank_html):
    h = lxml.html.fromstring(mbank_html)
    actions = []
    for entry in h.xpath('//tr/td[2]/text()')[2:]:
        g = INCOMING_RE.match(entry)
        if not g:
            continue
        action = g.groupdict()
        action['type'] = 'in_transfer'
        actions.append(action)
    return {'actions': actions}


def main(input_fpath):
    with open(input_fpath) as f:
        print(json.dumps(parse_mbank_html(f.read())))


if __name__ == '__main__':
    main(**parse_args())
