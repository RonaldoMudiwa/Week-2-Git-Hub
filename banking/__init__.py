"""Banking System.

A small bank: accounts, customers, transfers and statements. Everything most
code needs can be imported straight from here:

    from banking import CurrentAccount, SavingsAccount
"""

from .account import Account
from .current_account import CurrentAccount
from .enums import AccountStatus, TransactionType
from .exceptions import (
    AccountNotActiveError,
    BankError,
    InsufficientFundsError,
    ValidationError,
    WithdrawalError,
    WithdrawalLimitError,
)
from .money import format_money, to_money
from .savings_account import SavingsAccount
from .transaction import Transaction

__version__ = "0.1.0"

__all__ = [
    # Accounts
    "Account",
    "CurrentAccount",
    "SavingsAccount",
    "Transaction",
    # Choices
    "AccountStatus",
    "TransactionType",
    # Money
    "to_money",
    "format_money",
    # Errors
    "BankError",
    "ValidationError",
    "AccountNotActiveError",
    "WithdrawalError",
    "InsufficientFundsError",
    "WithdrawalLimitError",
    "__version__",
]
