#!/usr/bin/env python

"""ksiemgowy's main submodule, also used as an entry point. Contains the
logic used to generate database entries."""


import atexit
import os
import typing as T


import time
import logging


import schedule as schedule_module  # type: ignore

import ksiemgowy.mbankmail
import ksiemgowy.config
import ksiemgowy.models
import ksiemgowy.homepage_updater
import ksiemgowy.bookkeeping
import ksiemgowy.overdues

LOGGER = logging.getLogger("ksiemgowy.__main__")


@atexit.register
def atexit_handler(*_: T.Any, **__: T.Any) -> None:
    """Handles program termination in a predictable way."""
    LOGGER.info("Shutting down")


def every_seconds_do(
    num_seconds: int,
    called_fn: T.Callable[..., T.Any],
    args: T.Any,
    kwargs: T.Any,
) -> None:
    """A wrapper for "schedule" module. Intended to satisfy MyPy, as well as
    increasing testability by not relying on global state."""

    schedule_module.every(num_seconds).seconds.do(called_fn, *args, **kwargs)


def main_loop() -> None:
    """Main loop. Factored out for increased testability."""
    while True:
        schedule_module.run_pending()
        time.sleep(1)


def main(
    config: ksiemgowy.config.KsiemgowyConfig,
    database: ksiemgowy.models.KsiemgowyDB,
    homepage_update: T.Callable[
        [
            ksiemgowy.models.KsiemgowyDB,
            ksiemgowy.config.HomepageUpdaterConfig,
            ksiemgowy.config.ReportBuilderConfig
        ],
        None,
    ],
    register_fn: T.Callable[[int, T.Callable[..., T.Any], T.Any, T.Any], None],
    main_loop_fn: T.Callable[[], None],
) -> None:
    """Program's entry point. Schedules periodic execution of all routines."""

    LOGGER.info("ksiemgowyd started")

    for account in config.accounts:
        args = account.__dict__
        args["mbank_anonymization_key"] = config.mbank_anonymization_key
        args["database"] = database
        ksiemgowy.bookkeeping.check_for_updates(
            config.mbank_anonymization_key,
            database,
            account.mail_config,
            account.acc_number,
            config.should_send_mail,
        )

        register_fn(
            3600,
            ksiemgowy.bookkeeping.check_for_updates,
            [
                config.mbank_anonymization_key,
                database,
                account.mail_config,
                account.acc_number,
                config.should_send_mail,
            ],
            {},
        )

    if config.should_send_mail:

        # use the last specified account for overdue notifications:
        overdue_account = config.get_account_for_overdue_notifications()

        # the weird schedule is supposed to try to accomodate different
        # lifestyles
        register_fn(
            3600,
            ksiemgowy.overdues.notify_about_overdues,
            [
                database,
                overdue_account.mail_config,
            ],
            {},
        )

    register_fn(
        3600,
        homepage_update,
        [
            database,
            config.homepage_updater_config,
            config.report_builder_config,
        ],
        {},
    )
    homepage_update(
        database,
        config.homepage_updater_config,
        config.report_builder_config,
    )

    main_loop_fn()


def entrypoint() -> None:
    """Program's entry point. Loads config, instantiates required objects
    and then runs the main function."""
    with open(
        os.environ.get("KSIEMGOWYD_CFG_FILE", "/etc/ksiemgowy/config.yaml"),
        encoding="utf8",
    ) as config_file:
        config = ksiemgowy.config.load_config(config_file)
    logging_format = "[%(asctime)s] " + logging.BASIC_FORMAT
    logging.basicConfig(level=config.log_level, format=logging_format)
    main(
        config,
        ksiemgowy.models.KsiemgowyDB(config.database_uri),
        ksiemgowy.homepage_updater.maybe_update,
        every_seconds_do,
        main_loop,
    )


if __name__ == "__main__":
    entrypoint()
