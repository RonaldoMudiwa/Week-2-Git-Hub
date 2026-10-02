"""All the errors this package can raise.

Everything inherits from BankError, so one except clause catches the lot.

    BankError
    |-- ValidationError
    |-- AccountNotActiveError
    |-- WithdrawalError
        |-- InsufficientFundsError
        |-- WithdrawalLimitError
"""

from __future__ import annotations


class BankError(Exception):
    """Base class for every error in this package. Never raised directly."""


class ValidationError(BankError):
    """A value isn't allowed, e.g. a negative amount or a blank name."""


class AccountNotActiveError(BankError):
    """The account is frozen or closed, so money can't move."""


class WithdrawalError(BankError):
    """The account's rules don't allow this withdrawal.

    Every account type may refuse a withdrawal for its own reasons, but it
    always raises this error or one of its children. Code that uses any
    account only needs to catch this one.
    """


class InsufficientFundsError(WithdrawalError):
    """Not enough money, including any overdraft."""


class WithdrawalLimitError(WithdrawalError):
    """Too many withdrawals this month for this kind of account."""
