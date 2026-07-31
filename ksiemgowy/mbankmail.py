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

from email.message import Message
from typing import Dict, List, Tuple, Iterator, Optional

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

DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


class MbankParseError(Exception):
    """Raised when an attachment contains what look like transactions, but
    no date header could be found to timestamp them with."""


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

    sender_acc_no: str
    recipient_acc_no: str
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
        new.sender_acc_no = anonymize(
            self.sender_acc_no, mbank_anonymization_key
        )
        new.recipient_acc_no = anonymize(
            self.recipient_acc_no, mbank_anonymization_key
        )
        new.in_person = anonymize(self.in_person, mbank_anonymization_key)
        new.in_desc = anonymize(self.in_desc, mbank_anonymization_key)
        return new

    def get_timestamp(self) -> datetime.datetime:
        """Returns timestamp. This is there because we currently store the
        timestamp as string for rather random reasons."""
        return dateutil.parser.parse(self.timestamp)

    asdict = dataclasses.asdict


# lxml-stubs does not cover lxml.html, so under `mypy --strict` every
# signature naming HtmlElement trips disallow_any_unimported. The annotation
# is kept for the reader and the resulting Any is silenced explicitly.
def _extract_date(  # type: ignore[no-any-unimported]
    html: lxml.html.HtmlElement,
) -> Optional[str]:
    """Extracts the report date from a header element. Up to 2026-07-13 mBank
    used <h5 class="znaki">, since 2026-07-15 it uses <h1 class="h1">. Rather
    than hardcoding a tag, look for a date in any header, so that the next
    redesign does not take the parser down with it."""
    for element in html.xpath("//h1 | //h2 | //h3 | //h4 | //h5 | //h6"):
        match = DATE_RE.search(element.text_content())
        if match:
            return str(match.group(1))
    return None


def _iter_action_matches(  # type: ignore[no-any-unimported]
    html: lxml.html.HtmlElement,
) -> Iterator[Tuple[str, "re.Match[str]"]]:
    """Yields (time, regex match) for every table row that describes a
    transfer."""
    rows = html.xpath("//tr")
    logging.debug("len(rows)=%r", len(rows))
    for row in rows:
        desc_e = row.xpath("./td[2]//text()")
        if not desc_e:
            logging.debug("Missing desc_e, skipping")
            continue
        # Join every text node: the new template splits the description with
        # inline elements, so taking only the first node would truncate it.
        desc_s = " ".join(desc_e).strip().replace("\n", "").replace("\r", "")
        logging.debug("desc_s=%r", desc_s)
        time_e = row.xpath("./td[1]")
        if not time_e:
            logging.debug("Missing time_e, skipping")
            continue
        time = time_e[0].text_content().strip()
        match = INCOMING_RE.match(desc_s)
        if not match:
            continue
        yield time, match


def parse_mbank_html(mbank_html: bytes) -> Dict[str, List[MbankAction]]:
    """Parses mBank .htm attachment file and generates a list of actions
    that were derived from it."""
    html = lxml.html.fromstring(mbank_html)
    actions = []
    matches = list(_iter_action_matches(html))

    # The date is resolved after collecting the rows, so that "this is not a
    # transaction e-mail" (empty, fine) can be told apart from "there are
    # transactions but no date to stamp them with" (loud failure - silently
    # returning nothing here would lose transfers).
    date = _extract_date(html)
    if date is None:
        if matches:
            raise MbankParseError(
                f"found {len(matches)} transaction rows, but no header "
                f"contains a date - mBank likely changed the template"
            )
        logging.warning("No date header and no transaction rows; skipping")
        return {"actions": []}

    for time, match in matches:
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
                sender_acc_no=action["sender_acc_no"],
                recipient_acc_no=action["recipient_acc_no"],
                amount_pln=float(action["amount_pln"]),
                in_person=action["in_person"],
                in_desc=action["in_desc"],
                balance=float(action["balance"]),
                timestamp=f"{date} {time}",
                action_type=action["action_type"],
            )
        )
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
