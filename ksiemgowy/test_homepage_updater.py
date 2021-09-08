#!/usr/bin/env python3

"""Tests current_report_builder submodule by loading a fixture and comparing
the result of how it was processed to the desired output."""

import datetime
import difflib
import pickle
import pprint
import sys

import ksiemgowy.models

import ksiemgowy.current_report_builder
from ksiemgowy.__main__ import parse_config_and_build_args


def compare_dicts(dict1, dict2):
    """Compares two dictionaries, returning a string in "diff" format."""
    return "\n" + "\n".join(
        difflib.ndiff(
            pprint.pformat(dict1).splitlines(),
            pprint.pformat(dict2).splitlines(),
        )
    )


if __name__ == "__main__":
    try:
        with open("testdata/input.pickle", "rb") as f:
            now = pickle.load(f)
            expenses = pickle.load(f)
            mbank_actions = pickle.load(f)
    except FileNotFoundError:
        args = parse_config_and_build_args()
        public_db_uri = args[0][-1]
        db = ksiemgowy.models.KsiemgowyDB(public_db_uri)
        now = datetime.datetime.now()
        expenses = list(db.list_expenses())
        mbank_actions = list(db.list_positive_transfers())
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
