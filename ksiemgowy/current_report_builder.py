#!/usr/bin/env python

"""Ksiemgowy's reporting module. Generates a dictionary that details
information about organization's current financial status."""

import datetime
import logging

from typing import (
    List,
    Dict,
    Tuple,
    Union,
    TypedDict,
    Iterable,
)

import dateutil.rrule

from ksiemgowy.mbankmail import MbankAction
from ksiemgowy.config import CategoryCriteria, ReportBuilderConfig


LOGGER = logging.getLogger("homepage_updater")
PERIOD_TYPES = ["monthly", "yearly", "quarterly"]


def determine_category(
    action: MbankAction, categories: List[CategoryCriteria]
) -> str:
    """Given an incoming action, determine what label to assign to it."""

    for category_criteria in categories:
        if category_criteria.matches(action):
            return category_criteria.category_name
    return "Pozostałe"


def get_period(timestamp: datetime.datetime, period_type: str) -> str:
    """Returns a period which a given timestamp belongs to, as a string."""
    if period_type == "yearly":
        return f"{timestamp.year}"
    if period_type == "monthly":
        return f"{timestamp.year}-{timestamp.month:02d}"
    if period_type == "quarterly":
        quarter = ((timestamp.month - 1) // 3) + 1
        return f"{timestamp.year}Q{quarter}"
    raise ValueError("Unexpected period_type: %r" % get_period)


def apply_positive_transfers(
    now: datetime.datetime,
    last_updated: datetime.datetime,
    positive_actions: Iterable[MbankAction],
    balances_by_account_labels: Dict[str, float],
    account_labels: Dict[str, str],
) -> Tuple[
    float, int, datetime.datetime, Dict[str, Dict[str, Dict[str, float]]]
]:
    """Apply all positive transfers both to balances_by_account_labels and
    periodic_income. Returns newly built periodic_expenses, as well as total
    money raised and current information about the number of members who
    paid dues and the datestamp of due last paid."""
    periodic_income: Dict[str, Dict[str, Dict[str, float]]] = {}
    observed_acc_numbers = set()
    observed_acc_owners = set()

    total = 0.0
    num_subscribers = 0
    month_ago = now - datetime.timedelta(days=31)
    for action in positive_actions:
        balances_by_account_labels.setdefault(
            account_labels[action.recipient_acc_no], 0.0
        )
        balances_by_account_labels[
            account_labels[action.recipient_acc_no]
        ] += action.amount_pln

        for period_type in PERIOD_TYPES:
            period = get_period(action.get_timestamp(), period_type)
            periodic_income.setdefault(period_type, {}).setdefault(
                period, {}
            ).setdefault("Suma", 0)
            periodic_income[period_type][period]["Suma"] += action.amount_pln

        if action.get_timestamp() >= month_ago:
            if last_updated is None or action.get_timestamp() > last_updated:
                last_updated = action.get_timestamp()
            if (
                action.recipient_acc_no not in observed_acc_numbers
                and action.in_person not in observed_acc_owners
            ):
                num_subscribers += 1
                observed_acc_numbers.add(action.sender_acc_no)
                observed_acc_owners.add(action.in_person)
            total += action.amount_pln

    return (
        total,
        num_subscribers,
        last_updated,
        periodic_income,
    )


def apply_expenses(
    expenses: Iterable[MbankAction],
    balances_by_account_labels: Dict[str, float],
    account_labels: Dict[str, str],
    categories: List[CategoryCriteria],
) -> Tuple[datetime.datetime, Dict[str, Dict[str, Dict[str, float]]]]:
    """Apply all expenses both to balances_by_account_labels and
    periodic_expenses. Returns newly built periodic_expenses."""
    last_updated = datetime.datetime(year=1970, month=1, day=1)
    periodic_expenses: Dict[str, Dict[str, Dict[str, float]]] = {}
    for action in expenses:
        balances_by_account_labels.setdefault(
            account_labels[action.sender_acc_no], 0.0
        )
        balances_by_account_labels[
            account_labels[action.sender_acc_no]
        ] -= action.amount_pln
        for period_type in PERIOD_TYPES:
            period = get_period(action.get_timestamp(), period_type)
            category = determine_category(action, categories)
            periodic_expenses.setdefault(period_type, {}).setdefault(
                period, {}
            ).setdefault(category, 0)
            periodic_expenses[period_type][period][
                category
            ] += action.amount_pln
        if last_updated is None or action.get_timestamp() > last_updated:
            last_updated = action.get_timestamp()

    return last_updated, periodic_expenses


def build_periodic_final_balance(
    periodic_income: Dict[str, Dict[str, Dict[str, float]]],
    periodic_expenses: Dict[str, Dict[str, Dict[str, float]]],
) -> Tuple[Dict[str, Dict[str, Dict[str, float]]], float]:
    """Calculates periodic final balances, given all of the actions - an amount
    that specifies whether we accumulated more than we spent, or otherwise."""
    periodic_final_balance: Dict[str, Dict[str, Dict[str, float]]] = {}

    for period_type in PERIOD_TYPES:
        balance_so_far = 0.0
        periods = set(periodic_income.get(period_type, {}).keys()).union(
            set(periodic_expenses.get(period_type, {}).keys())
        )

        for period in sorted(periods):
            _periodic_income = sum(
                periodic_income.get(period_type, {}).get(period, {}).values()
            )
            _periodic_expenses = sum(
                periodic_expenses.get(period_type, {}).get(period, {}).values()
            )
            balance_so_far += _periodic_income - _periodic_expenses
            periodic_final_balance.setdefault(period_type, {}).setdefault(
                period, {}
            ).setdefault("Suma", 0)
            periodic_final_balance[period_type][period][
                "Suma"
            ] = balance_so_far
    return periodic_final_balance, balance_so_far


def build_periodic_balance(
    periodic_income: Dict[str, Dict[str, Dict[str, Union[float, int]]]],
    periodic_expenses: Dict[str, Dict[str, Dict[str, float]]],
) -> Dict[str, Dict[str, Dict[str, Union[float, int]]]]:
    """Calculates balances for each of the periods - the final amount of money
    on all of our accounts at the end of the period."""

    ret = {}
    for period_type in PERIOD_TYPES:
        periods = set(periodic_income.get(period_type, {}).keys()).union(
            set(periodic_expenses.get(period_type, {}).keys())
        )

        ret[period_type] = {
            period: {
                "Suma": sum(
                    x
                    for x in periodic_income.get(period_type, {})
                    .get(period, {})
                    .values()
                )
                - sum(
                    x
                    for x in periodic_expenses.get(period_type, {})
                    .get(period, {})
                    .values()
                )
            }
            for period in periods
        }

    return ret


def build_extra_monthly_reservations(
    now: datetime.datetime,
    extra_monthly_reservations_started_date: datetime.datetime,
) -> int:
    """Returns all extra monthly reservations collected until now.
    On 24 November 2020, we agreed that we'll be continuing to increase our
    reserves by 200 PLN each month."""
    return sum(
        [
            200
            for _ in dateutil.rrule.rrule(
                dateutil.rrule.MONTHLY,
                # https://pad.hs-ldz.pl/aPQpWcUbTvWwEdwsxB0ulQ#Kwestia-sk%C5%82adek
                dtstart=extra_monthly_reservations_started_date,
                until=now,
            )
        ]
    )


T_PERIODIC_REPORT = TypedDict(
    "T_PERIODIC_REPORT",
    {
        "Wydatki": Dict[str, Dict[str, Dict[str, float]]],
        "Przychody": Dict[str, Dict[str, Dict[str, float]]],
        "Bilans": Dict[str, Dict[str, Dict[str, float]]],
        "Saldo": Dict[str, Dict[str, Dict[str, float]]],
    },
)


T_CURRENT_REPORT = TypedDict(
    "T_CURRENT_REPORT",
    {
        "dues_total_lastmonth": float,
        "dues_last_updated": str,
        "dues_num_subscribers": int,
        "extra_monthly_reservations": int,
        "balance_so_far": float,
        "balances_by_account_labels": Dict[str, float],
        "by_period": T_PERIODIC_REPORT,
    },
)


def get_current_report(
    now: datetime.datetime,
    expenses: Iterable[MbankAction],
    positive_actions: Iterable[MbankAction],
    report_builder_config: ReportBuilderConfig,
) -> T_CURRENT_REPORT:
    """Module's entry point. Given time, expenses and income,
    generates a periodic summary of actions that happened on the accounts."""

    balances_by_account_labels: Dict[str, float] = {}

    last_updated, periodic_expenses = apply_expenses(
        expenses,
        balances_by_account_labels,
        report_builder_config.account_labels,
        report_builder_config.categories,
    )

    (
        total,
        num_subscribers,
        last_updated,
        periodic_income,
    ) = apply_positive_transfers(
        now,
        last_updated,
        positive_actions,
        balances_by_account_labels,
        report_builder_config.account_labels,
    )

    periodic_final_balance, balance_so_far = build_periodic_final_balance(
        periodic_income, periodic_expenses
    )

    ret: T_CURRENT_REPORT = {
        "dues_total_lastmonth": total,
        "dues_last_updated": last_updated.strftime("%d-%m-%Y"),
        "dues_num_subscribers": num_subscribers,
        "extra_monthly_reservations": build_extra_monthly_reservations(
            now, report_builder_config.extra_monthly_reservations_started_date
        ),
        "balance_so_far": balance_so_far,
        "balances_by_account_labels": balances_by_account_labels,
        "by_period": {
            "Wydatki": periodic_expenses,
            "Przychody": periodic_income,
            "Bilans": build_periodic_balance(
                periodic_income, periodic_expenses
            ),
            "Saldo": periodic_final_balance,
        },
    }
    LOGGER.debug("get_current_report_dues: ret=%r", ret)
    return ret
