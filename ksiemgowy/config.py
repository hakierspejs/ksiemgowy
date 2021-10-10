"""Groups together all code related to the handling of ksiemgowy's
configuration."""

import smtplib
import imaplib
import contextlib
import typing as T

from dataclasses import dataclass
import yaml

SEND_EMAIL = True
IMAP_FILTER = '(SINCE "02-Apr-2020" FROM "kontakt@mbank.pl")'


@dataclass(frozen=True)
class MailConfig:
    """A structure that stores our mail credentials and exposes an interface
    that allows the user to create SMTP and IMAP connections. Tested with
    GMail."""

    login: str
    password: str
    server: str

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
    deploy_key_path: str
    accounts: T.List[KsiemgowyAccount]
    mbank_anonymization_key: bytes

    def get_account_for_overdue_notifications(self) -> KsiemgowyAccount:
        """Returns an e-mail account used for overdue notifications. Currently
        it's the last one mentioned in the configuration."""
        return self.accounts[-1]


def load_config(
    config_file: T.IO[T.Any], env: T.Dict[str, str]
) -> KsiemgowyConfig:
    """Parses the configuration file and builds arguments for all routines."""
    mbank_anonymization_key = env["MBANK_ANONYMIZATION_KEY"].encode()
    config = yaml.load(config_file)
    accounts = []
    database_uri = config["PUBLIC_DB_URI"]
    deploy_key_path = env["DEPLOY_KEY_PATH"]
    for account in config["ACCOUNTS"]:
        imap_login = account["IMAP_LOGIN"]
        imap_server = account["IMAP_SERVER"]
        imap_password = account["IMAP_PASSWORD"]
        acc_no = account["ACC_NO"]
        accounts.append(
            KsiemgowyAccount(
                acc_number=acc_no,
                mail_config=MailConfig(
                    login=imap_login,
                    password=imap_password,
                    server=imap_server,
                ),
            )
        )

    return KsiemgowyConfig(
        database_uri=database_uri,
        accounts=accounts,
        mbank_anonymization_key=mbank_anonymization_key,
        deploy_key_path=deploy_key_path,
    )
