"""A record of one movement of money in an account."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .enums import TransactionType
from .money import format_money


@dataclass(frozen=True)
class Transaction:
    """One line on a bank statement.

    frozen=True means it can't be changed once made, just like a real bank
    statement line can't be edited after the fact.
    """

    kind: TransactionType
    amount: Decimal  # always positive, kind says which way it went
    balance_after: Decimal
    description: str
    timestamp: datetime
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def signed_amount(self) -> Decimal:
        """Positive for money in, negative for money out."""
        return self.amount if self.kind.is_credit else -self.amount

    def summary_line(self) -> str:
        """One line, e.g. "2026-10-02 14:05  Deposit       +£50.00   £150.00  Wages"."""
        sign = "+" if self.kind.is_credit else "-"
        amount_text = f"{sign}{format_money(self.amount)}"
        return (
            f"{self.timestamp:%Y-%m-%d %H:%M}  "
            f"{self.kind.label:<13}"
            f"{amount_text:>11}  "
            f"{format_money(self.balance_after):>11}  "
            f"{self.description}"
        )
