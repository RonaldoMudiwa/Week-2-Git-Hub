"""Fixed lists of choices used across the package."""

from __future__ import annotations

from enum import Enum, unique


@unique
class TransactionType(Enum):
    """What kind of movement a transaction was."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    INTEREST = "interest"
    FEE = "fee"

    @property
    def is_credit(self) -> bool:
        """True if this kind adds money to the account."""
        return self in {TransactionType.DEPOSIT, TransactionType.TRANSFER_IN,
                        TransactionType.INTEREST}

    @property
    def label(self) -> str:
        """A display name, so "transfer_in" reads as "Transfer In"."""
        return self.value.replace("_", " ").title()


@unique
class AccountStatus(Enum):
    """Whether money can move in and out of an account."""

    OPEN = "open"
    FROZEN = "frozen"  # temporarily blocked, e.g. a lost card
    CLOSED = "closed"  # finished for good
