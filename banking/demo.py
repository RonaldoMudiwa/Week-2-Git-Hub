"""A quick tour of the bank with made up customers. Run it from the project root:

    python -m banking demo

Everything happens in memory or in a throwaway folder, so it never touches
the bank you use with the other commands.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from .bank import Bank
from .exceptions import BankError
from .money import format_money
from .policies import FlatMonthlyFee, OverdraftFee, TieredInterest
from .reports import BankReport, TextFormatter
from .statements import Statement
from .storage import JSONBankRepository


def main() -> None:
    bank = Bank("Mudiwa Bank")

    ronaldo = bank.add_customer("Ronaldo Mudiwa", "ronaldo@example.com")
    amara = bank.add_customer("Amara Okafor", "amara@example.com")

    current = bank.open_account(ronaldo.customer_id, "current", "250", overdraft_limit="200",
                                fee_policy=FlatMonthlyFee("3"))
    savings = bank.open_account(ronaldo.customer_id, "savings", "1000",
                                interest_rate="4.5", max_withdrawals_per_month=1)
    amara_current = bank.open_account(amara.customer_id, "current", "40", overdraft_limit="100",
                                      fee_policy=OverdraftFee("24", minimum="2"))
    bank.open_account(amara.customer_id, "savings", "6000",
                      interest_policy=TieredInterest([("1000", "2"), (None, "5")]))

    current.deposit("1850", "Wages")
    bank.transfer(current.account_number, savings.account_number, "300", "Monthly saving")
    bank.transfer(current.account_number, amara_current.account_number, "25", "Pizza money")
    bank.transfer(savings.account_number, current.account_number, "100")
    amara_current.withdraw("90", "Phone repair")  # puts Amara into her overdraft

    # Each account follows its own rules: Ronaldo's current account pays a
    # flat fee, Amara is charged for her overdraft, and the two savings
    # accounts earn interest in different ways.
    bank.run_month_end()

    show_statements(bank)
    show_reports(bank)
    print(f"\nTotal held by {bank.name}: {format_money(bank.total_deposits)}")

    show_saving_and_loading(bank)

    print("\nThings the bank refuses to do")
    print("-" * 74)
    attempts = [
        ("Same email twice", lambda: bank.add_customer("Ron", "RONALDO@example.com")),
        ("Transfer to the same account",
         lambda: bank.transfer(current.account_number, current.account_number, "5")),
        ("Open an unknown account type", lambda: bank.open_account(ronaldo.customer_id, "crypto")),
        ("Transfer from an account that doesn't exist",
         lambda: bank.transfer("99999999", current.account_number, "5")),
        ("Second savings withdrawal this month",
         lambda: bank.transfer(savings.account_number, current.account_number, "5")),
    ]
    for label, attempt in attempts:
        try:
            attempt()
        except BankError as error:
            print(f"{label}: {type(error).__name__}: {error}")


def show_statements(bank: Bank) -> None:
    """This month's statement for every account. Works for any kind of account."""
    formatter = TextFormatter()
    today = datetime.now()
    for account in bank:
        print()
        print(formatter.statement(Statement.for_month(account, today.year, today.month)))


def show_reports(bank: Bank) -> None:
    """The bank manager's view."""
    report = BankReport(bank)
    formatter = TextFormatter()
    today = datetime.now()
    sections = [
        ("Customers", formatter.customer_table(report.customer_summaries())),
        ("Account types", formatter.type_table(report.totals_by_account_type())),
        ("Overdrawn accounts", formatter.overdrawn_table(report.overdrawn_accounts())),
        ("This month", formatter.month_activity(report.month_activity(today.year, today.month))),
    ]
    for title, table in sections:
        print(f"\n=== {title} ===")
        print(table)


def show_saving_and_loading(bank: Bank) -> None:
    """Save the bank, load it back, and check nothing changed.

    Uses a throwaway folder, so the demo never leaves files behind.
    """
    print("\nSaving and loading")
    print("-" * 74)
    with tempfile.TemporaryDirectory() as folder:
        repository = JSONBankRepository(Path(folder) / "bank.json")
        repository.save(bank)
        loaded = repository.load()

    same_history = all(
        account.transactions == loaded.get_account(account.account_number).transactions
        for account in bank
    )
    print(f"Saved and loaded {len(loaded)} accounts for {len(loaded.customers)} customers")
    print(f"Same total after loading: {loaded.total_deposits == bank.total_deposits}")
    print(f"Same history on every account: {same_history}")

