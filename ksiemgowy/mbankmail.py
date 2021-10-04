#!/usr/bin/env pyhon

"""Parses mbank daily notification e-mails."""

import re
import argparse
import dataclasses
import pprint
import copy
import hashlib
import logging
import datetime
import dateutil.parser

import lxml.html
from email.message import Message
from typing import Dict, List


INCOMING_RE = re.compile(
    "^mBank: Przelew (?P<action_type>przych|wych)\\."
    " z rach\\. (?P<in_acc_no>[0-9.]{8,14})"
    " na rach\\. (?P<out_acc_no>[0-9.]{8,14})"
    " kwota (?P<amount_pln>\\d+,\\d{2}) PLN"
    " (od|dla) (?P<in_person>[^;]+); "
    "(?P<in_desc>.+); "
    "Dost\\. (?P<balance>\\d+,\\d{2}) PLN$"
)


def anonymize(hashed_string: str, mbank_anonymization_key: bytes) -> str:
    """Anonymizes an input string using mbank_anonymization_key as
    cryptographic pepper."""
    return hashlib.sha256(
        hashed_string.encode() + mbank_anonymization_key
    ).hexdigest()


# pylint: disable=too-many-instance-attributes
@dataclasses.dataclass
class MbankAction:
    """A container for all transfers, positive or negative."""

    in_acc_no: str
    out_acc_no: str
    amount_pln: float
    in_person: str
    in_desc: str
    balance: str
    timestamp: str
    action_type: str

    def anonymized(self, mbank_anonymization_key: bytes) -> "MbankAction":
        """Anonymizes all potentially sensitive fields using
        mbank_anonymization_key as cryptographic pepper."""
        new = copy.copy(self)
        new.in_acc_no = anonymize(self.in_acc_no, mbank_anonymization_key)
        new.out_acc_no = anonymize(self.out_acc_no, mbank_anonymization_key)
        new.in_person = anonymize(self.in_person, mbank_anonymization_key)
        new.in_desc = anonymize(self.in_desc, mbank_anonymization_key)
        return new

    def get_timestamp(self) -> datetime.datetime:
        return dateutil.parser.parse(self.timestamp)

    asdict = dataclasses.asdict


def parse_mbank_html(mbank_html: bytes) -> Dict[str, List[MbankAction]]:
    """Parses mBank .htm attachment file and generates a list of actions
    that were derived from it."""
    html = lxml.html.fromstring(mbank_html)
    date = html.xpath("//h5/text()")[0].split(" - ")[0]
    actions = []
    rows = html.xpath("//tr")[2:]
    logging.debug("len(rows)=%r", len(rows))
    for row in rows:
        desc_e = row.xpath(".//td[2]/text()")
        if not desc_e:
            logging.debug("Missing desc_e, skipping")
            continue
        desc_s = desc_e[0].strip().replace("\n", "")
        logging.debug("desc_s=%r", desc_s)
        time = row.xpath(".//td[1]")[0].text_content().strip()
        match = INCOMING_RE.match(desc_s)
        if not match:
            continue
        action = {}
        action.update(match.groupdict())
        action["action_type"] = {
            "przych": "in_transfer",
            "wych": "out_transfer",
        }.get(action["action_type"], "other")
        actions.append(MbankAction(
            timestamp=f"{date} {time}",
            amount_pln=float(action.pop("amount_pln").replace(",", ".")),
            **action
        ))
    return {"actions": actions}


def parse_mbank_email(msg: Message) -> Dict[str, List[MbankAction]]:
    """Finds attachment with mBank account update in an .eml mBank email,
    then behaves like parse_mbank_html."""
    parsed = {}
    for part in msg.walk():
        params = dict(part.get_params())
        if "name" not in params or part.get_content_type() != "text/html":
            continue
        parsed = parse_mbank_html(part.get_payload(decode=True))
        if parsed["actions"]:
            break
    return parsed


def parse_args() -> Dict[str, str]:
    """Parses command-line arguments and returns them in a form usable as
    **kwargs."""
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("-i", "--input-fpath", required=True)
    parser.add_argument("-L", "--loglevel", default="DEBUG")
    parser.add_argument("--mode", choices=["html"], required=True)
    return parser.parse_args().__dict__


def main(input_fpath: str, mode: str, loglevel: str) -> None:
    """Entry point for the submodule, used for diagnostics. Reads data from
    input_fpath, then runs either parse_mbank_html or parse_mbank_email,
    depending on the mode."""
    logging.basicConfig(level=loglevel.upper())
    with open(input_fpath, "rb") as input_file:
        input_string = input_file.read()
    if mode == "html":
        result = parse_mbank_html(input_string)
    else:
        raise RuntimeError("Unexpected mode: %s" % mode)
    pprint.pprint(result)


if __name__ == "__main__":
    main(**parse_args())
