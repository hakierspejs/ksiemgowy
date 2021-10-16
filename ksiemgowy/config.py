"""Groups together all code related to the handling of ksiemgowy's
configuration."""

import smtplib
import imaplib
import contextlib
import typing as T

from dataclasses import dataclass
import yaml


@dataclass(frozen=True)
class MailConfig:
    """A structure that stores our mail credentials and exposes an interface
    that allows the user to create SMTP and IMAP connections. Tested with
    GMail."""

    login: str
    password: str
    server: str
    imap_filter: str

    def imap_connect(self) -> imaplib.IMAP4_SSL:
        """Logs in to IMAP using given credentials."""
        mail = imaplib.IMAP4_SSL(self.server)
        mail.login(self.login, self.password)
        return mail

    @contextlib.contextmanager
    def smtp_login(self) -> T.Generator[smtplib.SMTP_SSL, None, None]:
        """A context manager that handles SMTP login and logout."""
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.ehlo()
        server.login(self.login, self.password)
        yield server
        server.quit()


@dataclass(frozen=True)
class GitUpdaterConfig:
    """Stores information tied to the Git part of the homepage updater module.
    Basically: where's the repo, which credentials to use and which file to
    update."""

    git_url: str
    deploy_key_path: str
    dues_file_path: str


@dataclass(frozen=True)
class KsiemgowyAccount:
    """Stores information tied to a specific bank account: its number and
    an e-mail configuration used to handle communications related to it."""

    acc_number: str
    mail_config: MailConfig


@dataclass(frozen=True)
class KsiemgowyConfig:
    """Stores information required to start Ksiemgowy. This includes
    database, e-mail and website credentials, as well as cryptographic pepper
    used to anonymize account data."""

    database_uri: str
    accounts: T.List[KsiemgowyAccount]
    mbank_anonymization_key: bytes
    should_send_mail: bool
    git_updater_config: GitUpdaterConfig
    graphite_host: str
    graphite_port: int

    def get_account_for_overdue_notifications(self) -> KsiemgowyAccount:
        """Returns an e-mail account used for overdue notifications. Currently
        it's the last one mentioned in the configuration."""
        return self.accounts[-1]


def load_config(config_file: T.IO[T.Any]) -> KsiemgowyConfig:
    """Parses the configuration file and builds arguments for all routines."""
    config = yaml.load(config_file, yaml.SafeLoader)
    accounts = []
    deploy_key_path = config["DEPLOY_KEY_PATH"]
    git_url = config["HOMEPAGE_GIT_REPO_URL"]
    dues_file_path = config["DUES_FILE_PATH"]
    for account in config["ACCOUNTS"]:
        imap_login = account["IMAP_LOGIN"]
        imap_server = account["IMAP_SERVER"]
        imap_password = account["IMAP_PASSWORD"]
        imap_filter = account["IMAP_FILTER"]
        acc_no = account["ACC_NO"]
        accounts.append(
            KsiemgowyAccount(
                acc_number=acc_no,
                mail_config=MailConfig(
                    login=imap_login,
                    password=imap_password,
                    server=imap_server,
                    imap_filter=imap_filter,
                ),
            )
        )

    return KsiemgowyConfig(
        database_uri=config["DATABASE_URI"],
        accounts=accounts,
        mbank_anonymization_key=config["MBANK_ANONYMIZATION_KEY"].encode(),
        should_send_mail=config["SEND_MAIL"],
        git_updater_config=GitUpdaterConfig(
            deploy_key_path=deploy_key_path,
            git_url=git_url,
            dues_file_path=dues_file_path,
        ),
        graphite_host=config["GRAPHITE_HOST"],
        graphite_port=int(config["GRAPHITE_PORT"]),
    )
