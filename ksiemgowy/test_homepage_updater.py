#!/usr/bin/env python3

import pprint
import sys
import difflib
import os
import pickle
import datetime
import yaml
import collections

import ksiemgowy.public_state

from yaml.representer import Representer

import ksiemgowy.current_report_builder

yaml.add_representer(collections.defaultdict, Representer.represent_dict)


def build_args():
    config = yaml.load(
        open(
            os.environ.get("KSIEMGOWYD_CFG_FILE", "/etc/ksiemgowy/config.yaml")
        )
    )
    ret = []
    public_db_uri = config["PUBLIC_DB_URI"]
    for account in config["ACCOUNTS"]:
        imap_login = account["IMAP_LOGIN"]
        imap_server = account["IMAP_SERVER"]
        imap_password = account["IMAP_PASSWORD"]
        acc_no = account["ACC_NO"]
        ret.append(
            [
                imap_login,
                imap_password,
                imap_server,
                acc_no,
                public_db_uri,
            ]
        )
    return ret


def compare_dicts(d1, d2):
    return "\n" + "\n".join(
        difflib.ndiff(
            pprint.pformat(d1).splitlines(), pprint.pformat(d2).splitlines()
        )
    )


if __name__ == "__main__":
    try:
        with open("testdata/input.pickle", "rb") as f:
            now = pickle.load(f)
            expenses = pickle.load(f)
            mbank_actions = pickle.load(f)
    except FileNotFoundError:
        args = build_args()
        public_db_uri = args[0][-1]
        db = ksiemgowy.public_state.PublicState(public_db_uri)
        now = datetime.datetime.now()
        expenses = list(db.list_expenses())
        mbank_actions = list(db.list_mbank_actions())
        with open("testdata/input.pickle", "wb") as f:
            pickle.dump(now, f)
            pickle.dump(expenses, f)
            pickle.dump(mbank_actions, f)
    try:
        with open("testdata/expected_output.pickle", "rb") as f:
            expected_output = pickle.load(f)
            current_report = (
                ksiemgowy.current_report_builder.get_current_report(
                    now, expenses, mbank_actions
                )
            )
            if current_report == expected_output:
                print("Test passed")
            else:
                print(compare_dicts(current_report, expected_output))
                sys.exit("ERROR: test not passed.")
    except FileNotFoundError:
        current_report = ksiemgowy.current_report_builder.get_current_report(
            now, expenses, mbank_actions
        )
        with open("testdata/expected_output.pickle", "wb") as f:
            pickle.dump(current_report, f)
