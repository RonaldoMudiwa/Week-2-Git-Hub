"""A quick demo of the accounts. Run it from the project root:

    python -m banking

Temporary. A proper command line interface replaces it later in the week.
"""

from __future__ import annotations

from .account import Account
from .current_account import CurrentAccount
from .exceptions import BankError, WithdrawalError
from .savings_account import SavingsAccount


def show_statement(account: Account) -> None:
    """Print an account and its history. Works for any kind of account."""
    print(f"\n{account}")
    print("-" * 70)
    for transaction in account.transactions:
        print(transaction.summary_line())


def main() -> None:
    current = CurrentAccount("10000001", "Ronaldo Mudiwa", "120", overdraft_limit="200")
    savings = SavingsAccount("10000002", "Ronaldo Mudiwa", "1000", interest_rate="4.5",
                             max_withdrawals_per_month=2)

    current.deposit("1850", "Wages")
    current.withdraw("950", "Rent")
    current.withdraw("1100", "New laptop")  # dips into the overdraft
    savings.withdraw("150", "Holiday fund")
    savings.withdraw("50", "Birthday present")

    for account in (current, savings):
        show_statement(account)

    print(f"\nCurrent account overdrawn? {current.is_overdrawn}")

    print("\nThings the accounts refuse to do")
    print("-" * 70)
    attempts = [
        ("Spend past the overdraft", lambda: current.withdraw("500")),
        ("Third savings withdrawal this month", lambda: savings.withdraw("10")),
        ("Deposit a negative amount", lambda: savings.deposit("-5")),
        ("Close an account with money in it", savings.close),
    ]
    for label, attempt in attempts:
        try:
            attempt()
        except WithdrawalError as error:
            # Catches both InsufficientFundsError and WithdrawalLimitError.
            print(f"{label}: {type(error).__name__}: {error}")
        except BankError as error:
            print(f"{label}: {type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
