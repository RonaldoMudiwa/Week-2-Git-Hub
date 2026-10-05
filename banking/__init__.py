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
    StorageError,
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
from .reports import BankReport, CustomerSummary, MonthActivity, TextFormatter, TypeSummary
from .savings_account import SavingsAccount
from .statements import Statement
from .storage import BankRepository, InMemoryBankRepository, JSONBankRepository
from .transaction import Transaction

__version__ = "0.5.0"

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
    # Statements and reports
    "Statement",
    "BankReport",
    "TextFormatter",
    "CustomerSummary",
    "TypeSummary",
    "MonthActivity",
    # Saving and loading
    "BankRepository",
    "JSONBankRepository",
    "InMemoryBankRepository",
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
    "StorageError",
    "__version__",
]
