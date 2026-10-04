"""A record of one movement of money in an account."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from .enums import TransactionType
from .exceptions import ValidationError
from .money import format_money, to_money


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

    def to_dict(self) -> dict[str, Any]:
        """A plain dictionary that can be saved as JSON."""
        return {
            "transaction_id": self.transaction_id,
            "kind": self.kind.value,
            "amount": str(self.amount),  # text keeps the pennies exact
            "balance_after": str(self.balance_after),
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        """Rebuild a transaction from what to_dict made.

        Raises:
            ValidationError: If a value is missing or not valid.
        """
        try:
            return cls(
                kind=TransactionType(data["kind"]),
                amount=to_money(data["amount"]),
                balance_after=to_money(data["balance_after"]),
                description=data["description"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                transaction_id=data["transaction_id"],
            )
        except KeyError as error:
            raise ValidationError(f"Transaction is missing {error}.") from error
        except (ValueError, TypeError) as error:
            raise ValidationError(f"Transaction has a bad value: {error}") from error

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
