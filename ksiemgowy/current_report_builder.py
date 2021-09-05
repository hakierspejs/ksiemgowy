#!/usr/bin/env python

import datetime
import dateutil.rrule
import logging


LOGGER = logging.getLogger("homepage_updater")
ACCOUNT_LABELS = {
    ("76561893"): "Konto Jacka",
    (
        "1f328d38b05ea11998bac3ee0a4a2c6c9595e6848d22f66a47aa4a68f3b781ed"
    ): "Konto Jacka",
    (
        "d66afcd5d08d61a5678dd3dd3fbb6b2f84985c5add8306e6b3a1c2df0e85f840"
    ): "Konto stowarzyszenia",
}

CORRECTIONS = {
    "ACCOUNT_CORRECTIONS": {
        "Konto Jacka": -347.53,
        "Konto stowarzyszenia": -727.53,
    },
    "MONTHLY_INCOME_CORRECTIONS": {
        "2020-04": {"Suma": 200},
        "2020-05": {"Suma": 100},
    },
    "MONTHLY_EXPENSE_CORRECTIONS": {
        "2020-08": {"Meetup": 294.36},
        "2020-10": {"Remont": 1145},
        "2020-11": {"Pozostałe": 139.80},
        "2021-01": {
            "Drukarka HP": 314.00,
            "Meetup (za 6 mies.)": 285.43,
        },
        "2021-02": {"Domena": 55.34},
        "2021-05": {"Pozostałe": 200.0},
        "2021-07": {"Meetup (za 6 mies.)": 301.07},
        "2021-08": {"Zakupy": 840.04},
    },
}


def apply_corrections(
    corrections, balances_by_account_labels, monthly_income, monthly_expenses
):
    # Te hacki wynikają z bugów w powiadomieniach mBanku i braku powiadomień
    # związanych z przelewami własnymi:
    apply_d33tah_dues(monthly_income, balances_by_account_labels)
    for account_name, value in corrections["ACCOUNT_CORRECTIONS"].items():
        if account_name not in balances_by_account_labels:
            raise RuntimeError(
                "%r not in balances_by_account_labels" % account_name
            )
        balances_by_account_labels.setdefault(account_name, 0.0)
        balances_by_account_labels[account_name] += value

    balances_by_account_labels = dict(balances_by_account_labels)

    for month in corrections["MONTHLY_INCOME_CORRECTIONS"]:
        for label, value in corrections["MONTHLY_INCOME_CORRECTIONS"][
            month
        ].items():
            monthly_income.setdefault(month, {}).setdefault(label, 0)
            monthly_income[month][label] += value

    for month in corrections["MONTHLY_EXPENSE_CORRECTIONS"]:
        for label, value in corrections["MONTHLY_EXPENSE_CORRECTIONS"][
            month
        ].items():
            monthly_expenses.setdefault(month, {}).setdefault(label, 0)
            monthly_expenses[month][label] += value


def determine_category(action):
    if (
        action.out_acc_no == "5c0de18baddf47952"
        "002df587685dea519f06b639051ea3e4749ef058f6782bf"
    ):
        if int(action.amount_pln) == 800:
            return "Czynsz"
        else:
            return "Media (głównie prąd) i inne rozliczenia w zw. z lokalem"
    if (
        action.out_acc_no == "62eb7121a7ba81754aa746762dbc364e9ed961b"
        "8d1cf61a94d6531c92c81e56f"
    ):
        return "Internet"
    if (
        action.out_acc_no == "8f8340d7434997c052cc56f0191ed23d12a16ab1"
        "f2cba091c433539c13b7049c"
    ):
        return "Księgowość"
    return "Pozostałe"


def apply_d33tah_dues(monthly_income, balances_by_account_labels):
    first_200pln_d33tah_due_date = datetime.datetime(year=2020, month=6, day=7)
    # After this day, this hack isn't requried anymore:
    last_200pln_d33tah_due_date = datetime.datetime(year=2021, month=5, day=5)
    for timestamp in dateutil.rrule.rrule(
        dateutil.rrule.MONTHLY,
        dtstart=first_200pln_d33tah_due_date,
        until=last_200pln_d33tah_due_date,
    ):
        month = f"{timestamp.year}-{timestamp.month:02d}"
        monthly_income.setdefault(month, {}).setdefault("Suma", 0)
        monthly_income[month]["Suma"] += 200
        balances_by_account_labels.setdefault("Konto Jacka", 0.0)
        balances_by_account_labels["Konto Jacka"] += 200.0


def apply_positive_transfers(
    now, last_updated, mbank_actions, balances_by_account_labels
):
    monthly_income = {}
    observed_acc_numbers = set()
    observed_acc_owners = set()

    total = 0
    num_subscribers = 0
    month_ago = now - datetime.timedelta(days=31)
    for action in mbank_actions:
        balances_by_account_labels.setdefault(
            ACCOUNT_LABELS[action.out_acc_no], 0.0
        )
        balances_by_account_labels[
            ACCOUNT_LABELS[action.out_acc_no]
        ] += action.amount_pln

        month = f"{action.timestamp.year}-{action.timestamp.month:02d}"
        monthly_income.setdefault(month, {}).setdefault("Suma", 0)
        monthly_income[month]["Suma"] += action.amount_pln

        if action.timestamp < month_ago:
            continue
        if last_updated is None or action.timestamp > last_updated:
            last_updated = action.timestamp
        if (
            action.in_acc_no not in observed_acc_numbers
            and action.in_person not in observed_acc_owners
        ):
            num_subscribers += 1
            observed_acc_numbers.add(action.in_acc_no)
            observed_acc_owners.add(action.in_person)
        total += action.amount_pln

    return (
        total,
        num_subscribers,
        last_updated,
        monthly_income,
    )


def apply_expenses(expenses, balances_by_account_labels):
    last_updated = None
    monthly_expenses = {}
    for action in expenses:
        balances_by_account_labels.setdefault(
            ACCOUNT_LABELS[action.in_acc_no], 0.0
        )
        balances_by_account_labels[
            ACCOUNT_LABELS[action.in_acc_no]
        ] -= action.amount_pln
        month = f"{action.timestamp.year}-{action.timestamp.month:02d}"
        category = determine_category(action)
        monthly_expenses.setdefault(month, {}).setdefault(category, 0)
        monthly_expenses[month][category] += action.amount_pln
        if last_updated is None or action.timestamp > last_updated:
            last_updated = action.timestamp

    return last_updated, monthly_expenses


def build_monthly_final_balance(months, monthly_income, monthly_expenses):
    balance_so_far = 0
    monthly_final_balance = {}
    for month in sorted(months):
        _monthly_income = sum(monthly_income.get(month, {}).values())
        _monthly_expenses = sum(monthly_expenses.get(month, {}).values())
        balance_so_far += _monthly_income - _monthly_expenses
        monthly_final_balance.setdefault(month, {}).setdefault("Suma", 0)
        monthly_final_balance[month]["Suma"] = balance_so_far
    return monthly_final_balance, balance_so_far


def build_monthly_balance(months, monthly_income, monthly_expenses):
    return {
        month: {
            "Suma": sum(x for x in monthly_income.get(month, {}).values())
            - sum(x for x in monthly_expenses.get(month, {}).values())
        }
        for month in months
    }


def build_extra_monthly_reservations(now):
    return sum(
        [
            200
            for _ in dateutil.rrule.rrule(
                dateutil.rrule.MONTHLY,
                # https://pad.hs-ldz.pl/aPQpWcUbTvWwEdwsxB0ulQ#Kwestia-sk%C5%82adek
                dtstart=datetime.datetime(year=2020, month=11, day=24),
                until=now,
            )
        ]
    )


def get_current_report(now, expenses, mbank_actions, corrections=None):

    balances_by_account_labels = {}

    last_updated, monthly_expenses = apply_expenses(
        expenses,
        balances_by_account_labels,
    )

    (
        total,
        num_subscribers,
        last_updated,
        monthly_income,
    ) = apply_positive_transfers(
        now, last_updated, mbank_actions, balances_by_account_labels
    )

    if corrections is None:
        corrections = CORRECTIONS
    apply_corrections(
        corrections,
        balances_by_account_labels,
        monthly_income,
        monthly_expenses,
    )

    months = set(monthly_income.keys()).union(set(monthly_expenses.keys()))

    monthly_final_balance, balance_so_far = build_monthly_final_balance(
        months, monthly_income, monthly_expenses
    )

    ret = {
        "dues_total_lastmonth": total,
        "dues_last_updated": last_updated.strftime("%d-%m-%Y"),
        "dues_num_subscribers": num_subscribers,
        "extra_monthly_reservations": build_extra_monthly_reservations(now),
        "balance_so_far": balance_so_far,
        "balances_by_account_labels": balances_by_account_labels,
        "monthly": {
            "Wydatki": monthly_expenses,
            "Przychody": monthly_income,
            "Bilans": build_monthly_balance(
                months, monthly_income, monthly_expenses
            ),
            "Saldo": monthly_final_balance,
        },
    }
    LOGGER.debug("get_current_report_dues: ret=%r", ret)
    return ret
