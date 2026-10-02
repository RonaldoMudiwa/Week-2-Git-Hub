"""Banking System.

A small bank: accounts, customers, transfers and statements. Everything most
code needs can be imported straight from here:

    from banking import CurrentAccount, SavingsAccount
"""

from .account import Account
from .account_numbers import AccountNumberGenerator, SequentialAccountNumberGenerator
from .bank import Bank
from .current_account import CurrentAccount
from .customer import Customer
from .enums import AccountStatus, TransactionType
from .exceptions import (
    AccountNotActiveError,
    AccountNotFoundError,
    BankError,
    CustomerNotFoundError,
    DuplicateCustomerError,
    InsufficientFundsError,
    NotFoundError,
    ValidationError,
    WithdrawalError,
    WithdrawalLimitError,
)
from .money import format_money, to_money
from .policies import (
    CombinedFees,
    FeePolicy,
    FlatMonthlyFee,
    FlatRateInterest,
    InterestPolicy,
    NoFee,
    NoInterest,
    OverdraftFee,
    TieredInterest,
)
from .savings_account import SavingsAccount
from .transaction import Transaction

__version__ = "0.3.0"

__all__ = [
    # Bank
    "Bank",
    "Customer",
    "AccountNumberGenerator",
    "SequentialAccountNumberGenerator",
    # Accounts
    "Account",
    "CurrentAccount",
    "SavingsAccount",
    "Transaction",
    # Interest and fee rules
    "InterestPolicy",
    "NoInterest",
    "FlatRateInterest",
    "TieredInterest",
    "FeePolicy",
    "NoFee",
    "FlatMonthlyFee",
    "OverdraftFee",
    "CombinedFees",
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
    "NotFoundError",
    "CustomerNotFoundError",
    "AccountNotFoundError",
    "DuplicateCustomerError",
    "__version__",
]
