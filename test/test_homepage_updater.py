#!/usr/bin/env python3

import datetime
import unittest
import os
import subprocess

import ksiemgowy.models
import ksiemgowy.homepage_updater as M

from ksiemgowy.config import ReportBuilderConfig

EXAMPLE_SSH_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACCjlHgq6Q91LeX7ISEMZSJ7LBlQtM3xgKhMPxzoeifvxQAAAJgxKPDiMSjw
4gAAAAtzc2gtZWQyNTUxOQAAACCjlHgq6Q91LeX7ISEMZSJ7LBlQtM3xgKhMPxzoeifvxQ
AAAEBfn9aYPf1wFnQ9R303tTGKehEj1A1mTfRzDkJ1HRHd6KOUeCrpD3Ut5fshIQxlInss
GVC0zfGAqEw/HOh6J+/FAAAAEGQzM3RhaEBkMzN0YWgtcGMBAgMEBQ==
-----END OPENSSH PRIVATE KEY-----
"""


class HomepageUpdaterSystemTestCase(unittest.TestCase):
    def test_system(self):
        with open("/tmp/zxc", "w") as f:
            f.write(EXAMPLE_SSH_KEY)
        os.chmod("/tmp/zxc", 0o600)
        subprocess.check_call(["git", "init", "--bare", "/tmp/qwe3"])
        database_mock = ksiemgowy.models.KsiemgowyDB("sqlite://")
        M.maybe_update(
            database_mock,
            homepage_updater_config=ksiemgowy.config.HomepageUpdaterConfig(
                deploy_key_path="/tmp/zxc",
                git_url="/tmp/qwe3",
                dues_file_path="data.yml",
                graphite_host="127.0.0.1",
                graphite_port=31337,
            ),
            report_builder_config=ReportBuilderConfig(
                account_labels={},
                corrections_by_label={},
                monthly_income_corrections={},
                monthly_expense_corrections={},
                first_200pln_d33tah_due_date=datetime.datetime.now(),
                last_200pln_d33tah_due_date=datetime.datetime.now(),
                extra_monthly_reservations_started_date=datetime.datetime.now(),
            ),
        )
