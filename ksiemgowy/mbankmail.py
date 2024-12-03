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
import typing as T

from email.message import Message

import dateutil.parser
import lxml.html


INCOMING_RE = re.compile(
    "^mBank: Przelew (?P<action_type>przych|wych)\\."
    " z rach\\. (?P<sender_acc_no>[0-9.]{8,14})"
    " na rach\\. (?P<recipient_acc_no>[0-9.]{8,14})"
    " kwota (?P<amount_pln>\\d+,\\d{2}) PLN"
    " (od|dla) (?P<in_person>[^;]+); "
    "(?P<in_desc>.+); "
    "Dost\\. (?P<balance>\\d+,\\d{2}) PLN$"
)


def _expect_type(expected_type: T.Type[T.Any], item: T.Any) -> T.Any:
    if not isinstance(item, expected_type):
        raise ValueError(f"Expected {expected_type}, got {item!r}")
    return item


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

    recipient_acc_no: str
    sender_acc_no: str
    amount_pln: float
    in_person: str
    in_desc: str
    balance: float
    timestamp: str
    action_type: str

    def anonymized(self, mbank_anonymization_key: bytes) -> "MbankAction":
        """Anonymizes all potentially sensitive fields using
        mbank_anonymization_key as cryptographic pepper."""
        new = copy.copy(self)
        new.recipient_acc_no = anonymize(
            self.recipient_acc_no, mbank_anonymization_key
        )
        new.sender_acc_no = anonymize(
            self.sender_acc_no, mbank_anonymization_key
        )
        new.in_person = anonymize(self.in_person, mbank_anonymization_key)
        new.in_desc = anonymize(self.in_desc, mbank_anonymization_key)
        return new

    def get_timestamp(self) -> datetime.datetime:
        """Returns timestamp. This is there because we currently store the
        timestamp as string for rather random reasons."""
        return dateutil.parser.parse(self.timestamp)

    asdict = dataclasses.asdict


def parse_mbank_html(mbank_html: bytes) -> T.Dict[str, T.List[MbankAction]]:
    """Parses mBank .htm attachment file and generates a list of actions
    that were derived from it."""
    html = lxml.html.fromstring(mbank_html)
    h5_texts = _expect_type(list, html.xpath("//h5/text()"))
    date: str = h5_texts[0].split(" - ")[0]
    actions = []
    rows = _expect_type(list, html.xpath("//tr"))[2:]
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
        action["amount_pln"] = action["amount_pln"].replace(",", ".")
        action["balance"] = action["balance"].replace(",", ".")
        actions.append(
            MbankAction(
                recipient_acc_no=action["recipient_acc_no"],
                sender_acc_no=action["sender_acc_no"],
                amount_pln=float(action["amount_pln"]),
                in_person=action["in_person"],
                in_desc=action["in_desc"],
                balance=float(action["balance"]),
                timestamp=f"{date} {time}",
                action_type=action["action_type"],
            )
        )
    return {"actions": actions}


def parse_mbank_email(msg: Message) -> T.Dict[str, T.List[MbankAction]]:
    """Finds attachment with mBank account update in an .eml mBank email,
    then behaves like parse_mbank_html."""
    parsed = {}
    for part in msg.walk():
        params_raw = part.get_params()
        if params_raw is None:
            continue
        params = dict(params_raw)
        if "name" not in params or part.get_content_type() != "text/html":
            continue
        b = _expect_type(bytes, part.get_payload(decode=True))
        parsed = parse_mbank_html(b)
        if parsed["actions"]:
            break
    return parsed


def parse_args() -> T.Dict[str, str]:
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
        raise RuntimeError(f"Unexpected mode: {mode}")
    pprint.pprint(result)


if __name__ == "__main__":
    main(**parse_args())
