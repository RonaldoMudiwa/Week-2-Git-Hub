"""Bank statements: an account's activity over a stretch of time."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .account import Account
from .enums import TransactionType
from .exceptions import ValidationError
from .money import ZERO
from .transaction import Transaction


@dataclass(frozen=True)
class Statement:
    """What happened in one account between two dates, both days included.

    Like the paper statement a bank posts you: the balance at the start,
    every line in between, and the balance at the end. It is a snapshot, so
    it can't be changed after it is made.
    """

    account_number: str
    owner_name: str
    account_type: str
    start: date
    end: date
    opening_balance: Decimal
    lines: tuple[Transaction, ...]

    @classmethod
    def for_period(cls, account: Account, start: date, end: date) -> "Statement":
        """Build a statement for any dates.

        Raises:
            ValidationError: If start is after end.
        """
        if not (isinstance(start, date) and isinstance(end, date)):
            raise ValidationError("Statement dates must be dates.")
        if start > end:
            raise ValidationError(f"Start date {start} is after end date {end}.")

        opening = ZERO
        lines = []
        for transaction in account.transactions:
            day = transaction.timestamp.date()
            if day < start:
                # The last line before the period holds the opening balance.
                opening = transaction.balance_after
            elif day <= end:
                lines.append(transaction)

        return cls(account.account_number, account.owner_name, account.ACCOUNT_TYPE,
                   start, end, opening, tuple(lines))

    @classmethod
    def for_month(cls, account: Account, year: int, month: int) -> "Statement":
        """A statement for one calendar month, e.g. for_month(account, 2026, 10)."""
        if not 1 <= month <= 12:
            raise ValidationError(f"Month must be 1 to 12, got {month}.")
        last_day = calendar.monthrange(year, month)[1]  # handles leap years
        return cls.for_period(account, date(year, month, 1), date(year, month, last_day))

    @property
    def closing_balance(self) -> Decimal:
        return self.opening_balance + sum((t.signed_amount for t in self.lines), start=ZERO)

    @property
    def money_in(self) -> Decimal:
        return sum((t.amount for t in self.lines if t.kind.is_credit), start=ZERO)

    @property
    def money_out(self) -> Decimal:
        """Everything that left the account, shown as a positive number."""
        return sum((t.amount for t in self.lines if not t.kind.is_credit), start=ZERO)

    @property
    def interest_paid(self) -> Decimal:
        return self._total_of(TransactionType.INTEREST)

    @property
    def fees_charged(self) -> Decimal:
        return self._total_of(TransactionType.FEE)

    def _total_of(self, kind: TransactionType) -> Decimal:
        return sum((t.amount for t in self.lines if t.kind is kind), start=ZERO)
