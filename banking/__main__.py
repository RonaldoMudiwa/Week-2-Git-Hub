"""A quick demo of the bank. Run it from the project root:

    python -m banking

Temporary. A proper command line interface replaces it later in the week.
"""

from __future__ import annotations

from .account import Account
from .bank import Bank
from .exceptions import BankError
from .money import format_money


def show_statement(account: Account) -> None:
    """Print an account and its history. Works for any kind of account."""
    print(f"\n{account}")
    print("-" * 74)
    for transaction in account.transactions:
        print(transaction.summary_line())


def main() -> None:
    bank = Bank("Mudiwa Bank")

    ronaldo = bank.add_customer("Ronaldo Mudiwa", "ronaldo@example.com")
    amara = bank.add_customer("Amara Okafor", "amara@example.com")

    current = bank.open_account(ronaldo.customer_id, "current", "250", overdraft_limit="200")
    savings = bank.open_account(ronaldo.customer_id, "savings", "1000",
                                interest_rate="4.5", max_withdrawals_per_month=1)
    amara_current = bank.open_account(amara.customer_id, "current", "40")

    current.deposit("1850", "Wages")
    bank.transfer(current.account_number, savings.account_number, "300", "Monthly saving")
    bank.transfer(current.account_number, amara_current.account_number, "25", "Pizza money")
    bank.transfer(savings.account_number, current.account_number, "100")

    for customer in bank.customers:
        print(f"\n=== {customer} ===")
        for account in bank.accounts_for(customer.customer_id):
            show_statement(account)

    print(f"\nTotal held by {bank.name}: {format_money(bank.total_deposits)}")

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


if __name__ == "__main__":
    main()
