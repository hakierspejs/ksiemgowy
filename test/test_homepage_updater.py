#!/usr/bin/env python3

import datetime
import unittest
import os
import subprocess

import ksiemgowy.models
import ksiemgowy.homepage_updater as M

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
            "/tmp/zxc",
            git_url="/tmp/qwe3",
            dues_file_path="data.yml",
            corrections={
                "ACCOUNT_CORRECTIONS": {},
                "MONTHLY_INCOME_CORRECTIONS": {},
                "MONTHLY_EXPENSE_CORRECTIONS": {},
            },
        )
