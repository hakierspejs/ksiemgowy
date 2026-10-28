#!/usr/bin/env python3
"""Reveal mBank transfers or interactively assign emails to unknown senders.

Default mode:
  * read existing sender_acc_no_to_email entries;
  * find incoming transfers from unregistered sender accounts in the last 5 months;
  * find their source emails through IMAP and show original sender metadata;
  * ask for contact email once per sender account;
  * add the mapping with notify_arrived='n' and notify_overdue='n'.

Single-transfer mode remains available with --id or --message-id.
No confirmation or overdue emails are sent by this script.
"""

import argparse
import dataclasses
import datetime
import email
from email.utils import parseaddr
import json
import math
import os
import sys
from collections import defaultdict

import sqlalchemy
from dateutil.relativedelta import relativedelta

from ksiemgowy.config import load_config
from ksiemgowy.mbankmail import anonymize, parse_mbank_email


HASHED_FIELDS = ("sender_acc_no", "recipient_acc_no", "in_person", "in_desc")
DEFAULT_MAILBOXES = ("INBOX", "[Gmail]/All Mail")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--id", type=int, help="Reveal one bank_actions row")
    selector.add_argument("--message-id", help="Reveal one row by RFC 5322 Message-ID")
    parser.add_argument(
        "--config",
        default=os.environ.get("KSIEMGOWYD_CFG_FILE", "config.yaml"),
        help="Ksiemgowy YAML config (default: ./config.yaml)",
    )
    parser.add_argument(
        "--mailbox", action="append", metavar="FOLDER",
        help="IMAP folder to search; repeat for multiple folders "
             "(default: INBOX, then [Gmail]/All Mail)",
    )
    parser.add_argument("--months", type=int, default=5,
                        help="Look-back window for contact import (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show matches and prompt, but do not write to the database")
    parser.add_argument("--list-only", action="store_true",
                        help="Display contacts and matches without prompting or writing")
    parser.add_argument("--timestamp", help="Single-transfer mode: timestamp filter")
    parser.add_argument("--amount", type=float, help="Single-transfer mode: amount filter")
    parser.add_argument("--type", choices=("in_transfer", "out_transfer"),
                        help="Single-transfer mode: action type filter")
    args = parser.parse_args()
    if args.months <= 0:
        parser.error("--months must be positive")
    if args.id is None and args.message_id is None and (
        args.timestamp is not None or args.amount is not None or args.type is not None
    ):
        parser.error("--timestamp/--amount/--type require --id or --message-id")
    return args


def matches(action, row, key):
    """Compare an original parsed action against the anonymized DB row."""
    hashed = action.anonymized(key)
    if action.action_type != row["action_type"] or action.timestamp != row["timestamp"]:
        return False
    if any(getattr(hashed, field) != row[field] for field in HASHED_FIELDS):
        return False
    for field in ("amount_pln", "balance"):
        actual = float(getattr(action, field))
        expected = float(row[field])
        if field == "amount_pln":
            actual, expected = abs(actual), abs(expected)
        if not math.isclose(actual, expected, abs_tol=0.005, rel_tol=0):
            return False
    return True


class MailLookup:
    """Reuse IMAP connections and cache parsed email bodies per Message-ID."""

    def __init__(self, config, mailboxes):
        self.config = config
        self.mailboxes = mailboxes
        self.key = config.mbank_anonymization_key
        self.connections = {}
        self.cache = {}
        self.account_by_hash = {
            anonymize(account.acc_number, self.key): account
            for account in config.accounts
        }

    def close(self):
        for conn in self.connections.values():
            try:
                conn.logout()
            except Exception:
                # Best effort: do not hide the result if logout fails.
                pass
        self.connections.clear()

    def _get_connection(self, account):
        login = account.mail_config.login
        if login not in self.connections:
            self.connections[login] = account.mail_config.imap_connect()
        return self.connections[login]

    @staticmethod
    def _search_folder(mail, folder, message_id):
        status, _ = mail.select(folder, readonly=True)
        if status != "OK":
            return []
        status, data = mail.uid("SEARCH", None, "HEADER", "Message-ID", f'"{message_id}"')
        if status != "OK":
            raise RuntimeError(f"IMAP UID SEARCH failed for {folder!r}: {status}")
        result = []
        for uid in data[0].split() if data and data[0] else []:
            status, parts = mail.uid("FETCH", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            for part in parts:
                if not isinstance(part, tuple) or not isinstance(part[1], bytes):
                    continue
                msg = email.message_from_bytes(part[1])
                if (msg.get("Message-ID") or "").strip() == message_id:
                    result.extend(parse_mbank_email(msg).get("actions", []))
        return result

    def find_action(self, row):
        message_id = (row.get("source_message_id") or "").strip()
        if not message_id:
            return None, "brak source_message_id"
        if any(ch in message_id for ch in ('"', "\r", "\n")):
            return None, "nieprawidlowy Message-ID"

        observed_hash = (
            row["recipient_acc_no"] if row["action_type"] == "in_transfer"
            else row["sender_acc_no"]
        )
        accounts = ([self.account_by_hash[observed_hash]]
                    if observed_hash in self.account_by_hash else self.config.accounts)

        for account in accounts:
            cache_key = (account.mail_config.login, message_id)
            if cache_key not in self.cache:
                actions = []
                try:
                    mail = self._get_connection(account)
                    for folder in self.mailboxes:
                        actions = self._search_folder(mail, folder, message_id)
                        if actions:
                            break
                except Exception as exc:
                    self.cache[cache_key] = ([], f"blad IMAP: {exc}")
                else:
                    self.cache[cache_key] = (actions, None)
            actions, error = self.cache[cache_key]
            for action in actions:
                if matches(action, row, self.key):
                    return action, None
            if error:
                return None, error
        return None, "nie znaleziono pasujacej operacji w mailu"


def read_existing_contacts(engine):
    with engine.connect() as conn:
        rows = conn.execute(sqlalchemy.text(
            "SELECT sender_acc_no, email, notify_arrived, notify_overdue, is_member "
            "FROM sender_acc_no_to_email "
            "ORDER BY lower(email), sender_acc_no"
        )).mappings()
        return [dict(row) for row in rows]


def read_unknown_incoming(engine, known_by_account, config, months):
    cutoff = datetime.datetime.now() - relativedelta(months=months)
    observed_accounts = {
        anonymize(account.acc_number, config.mbank_anonymization_key)
        for account in config.accounts
    }
    synthetic_account = anonymize("AUTOCORRECTION", config.mbank_anonymization_key)
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(sqlalchemy.text(
            "SELECT * FROM bank_actions "
            "WHERE action_type = 'in_transfer' "
            "AND timestamp >= :cutoff AND timestamp <= :now "
            "ORDER BY sender_acc_no, timestamp, id"
        ), {
            "cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
            "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }).mappings()]

    unknown = defaultdict(list)
    for row in rows:
        sender = row["sender_acc_no"]
        if sender == synthetic_account or row["recipient_acc_no"] not in observed_accounts:
            continue
        if sender in known_by_account and (known_by_account[sender].get("email") or "").strip():
            continue
        unknown[sender].append(row)
    return cutoff, unknown


def valid_email(value):
    parsed_name, addr = parseaddr(value)
    if parsed_name or addr != value or value.count("@") != 1:
        return False
    local, domain = value.rsplit("@", 1)
    return bool(local and domain and "." in domain and not any(c.isspace() for c in value))


def save_email(engine, sender_hash, address):
    """Never overwrite an existing nonblank email; disable both notifications."""
    with engine.begin() as conn:
        row = conn.execute(sqlalchemy.text(
            "SELECT email FROM sender_acc_no_to_email WHERE sender_acc_no = :sender"
        ), {"sender": sender_hash}).mappings().first()
        if row is not None and (row["email"] or "").strip():
            return False, "nadawca ma juz adres w bazie; nie nadpisano"
        if row is None:
            conn.execute(sqlalchemy.text(
                "INSERT INTO sender_acc_no_to_email "
                "(sender_acc_no, email, notify_arrived, notify_overdue, is_member) "
                "VALUES (:sender, :email, 'n', 'n', 'n')"
            ), {"sender": sender_hash, "email": address})
        else:
            conn.execute(sqlalchemy.text(
                "UPDATE sender_acc_no_to_email "
                "SET email = :email, notify_arrived = 'n', notify_overdue = 'n' "
                "WHERE sender_acc_no = :sender"
            ), {"sender": sender_hash, "email": address})
    return True, "zapisano (notify_arrived=n, notify_overdue=n)"


def print_known_contacts(known):
    print(f"\n=== ZNANE KONTAKTY: {len(known)} ===")
    for row in known:
        print(f"{str(row['email'] or '(brak e-maila)'):<42} "
              f"konto={row['sender_acc_no'][:12]}... "
              f"arrived={row['notify_arrived']} overdue={row['notify_overdue']}")


def import_contacts(engine, config, args, lookup):
    known = read_existing_contacts(engine)
    known_by_account = {row["sender_acc_no"]: row for row in known}
    print_known_contacts(known)

    cutoff, unknown = read_unknown_incoming(engine, known_by_account, config, args.months)
    print(f"\n=== NIEZNANI NADAWCY od {cutoff:%Y-%m-%d}: "
          f"{len(unknown)} kont, {sum(map(len, unknown.values()))} przelewow ===")
    added = skipped = unresolved = 0

    for number, (sender, rows) in enumerate(unknown.items(), 1):
        print("\n" + "=" * 70)
        print(f"[{number}/{len(unknown)}] konto nadawcy (hash): {sender}")
        print(f"Wpłaty: {len(rows)}, łączna kwota: {sum(float(r['amount_pln']) for r in rows):.2f} PLN")
        names = set()
        decoded = 0
        for row in rows:
            action, problem = lookup.find_action(row)
            if action is None:
                print(f"  id={row['id']}  {row['timestamp']}  {row['amount_pln']:.2f} PLN "
                      f"[nieodczytany oryginal: {problem}]")
                continue
            decoded += 1
            names.add(action.in_person)
            print(f"  id={row['id']}  {row['timestamp']}  {row['amount_pln']:.2f} PLN")
            print(f"    nadawca: {action.in_person}")
            print(f"    rachunek: {action.sender_acc_no}")
            print(f"    tytul: {action.in_desc}")
        if len(names) > 1:
            print("  UWAGA: rozne opisy nadawcy dla tego samego rachunku!")
        if not decoded:
            print("  Brak wiarygodnego dopasowania do oryginalnego maila; "
                  "pomijam zapis, by nie przypisac adresu do zlej osoby.")
            unresolved += 1
            continue
        if args.list_only:
            continue

        while True:
            try:
                address = input("Adres e-mail (Enter=pomin, q=zakoncz): ").strip()
            except EOFError:
                print("\nKoniec stdin, przerywam.")
                return
            if address.lower() == "q":
                print("Przerwano na zadanie uzytkownika.")
                return
            if not address:
                skipped += 1
                break
            if not valid_email(address):
                print("Nieprawidlowy adres e-mail; sprobuj ponownie.")
                continue
            if args.dry_run:
                print(f"DRY RUN: dodalbym {address} z notify_arrived=n, notify_overdue=n")
                added += 1
                break
            try:
                result, msg = save_email(engine, sender, address)
            except sqlalchemy.exc.SQLAlchemyError as exc:
                print(f"BLAD ZAPISU: {exc}", file=sys.stderr)
                skipped += 1
                break
            print(msg)
            if result:
                added += 1
            else:
                skipped += 1
            break

    print(f"\nGotowe: {'symulowanych' if args.dry_run else 'dodanych'} {added}; "
          f"pominietych {skipped}; bez identyfikacji {unresolved}.")


def read_single_row(engine, args):
    if args.id is not None:
        statement = "SELECT * FROM bank_actions WHERE id = :identifier"
        params = {"identifier": args.id}
    else:
        statement = "SELECT * FROM bank_actions WHERE source_message_id = :identifier "
        statement += "ORDER BY timestamp, id"
        params = {"identifier": args.message_id}
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(sqlalchemy.text(statement), params).mappings()]
    if args.timestamp:
        rows = [r for r in rows if r["timestamp"] == args.timestamp]
    if args.type:
        rows = [r for r in rows if r["action_type"] == args.type]
    if args.amount is not None:
        rows = [r for r in rows if math.isclose(abs(float(r["amount_pln"])),
                abs(args.amount), rel_tol=0, abs_tol=0.005)]
    if len(rows) != 1:
        raise RuntimeError(f"Oczekiwano jednego rekordu, znaleziono {len(rows)}. "
                           "Wybierz konkretny rekord przez --id.")
    return rows[0]


def main():
    args = parse_args()
    with open(args.config, encoding="utf-8") as f:
        config = load_config(f)
    engine = sqlalchemy.create_engine(config.database_uri)
    columns = {c["name"] for c in sqlalchemy.inspect(engine).get_columns("bank_actions")}
    if "source_message_id" not in columns:
        engine.dispose()
        raise RuntimeError("Brakuje kolumny bank_actions.source_message_id; "
                           "najpierw wdroz migracje dodajaca Message-ID.")
    lookup = MailLookup(config, args.mailbox or DEFAULT_MAILBOXES)
    try:
        if args.id is not None or args.message_id is not None:
            row = read_single_row(engine, args)
            action, problem = lookup.find_action(row)
            if action is None:
                raise RuntimeError(f"Brak dopasowania dla id={row['id']}: {problem}")
            print(json.dumps({
                "bank_actions_id": row["id"],
                "source_message_id": row.get("source_message_id"),
                "original_action": dataclasses.asdict(action),
            }, indent=2, ensure_ascii=False))
        else:
            import_contacts(engine, config, args, lookup)
    finally:
        lookup.close()
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, sqlalchemy.exc.SQLAlchemyError) as exc:
        print(f"Blad: {exc}", file=sys.stderr)
        sys.exit(1)
