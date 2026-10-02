"""Where new account numbers come from.

The Bank only knows about AccountNumberGenerator, not any particular way of
making numbers. So the numbering scheme can change without touching the
Bank, and tests can hand it predictable numbers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .exceptions import ValidationError

ACCOUNT_NUMBER_LENGTH = 8  # UK account numbers are 8 digits


class AccountNumberGenerator(ABC):
    """Anything that can hand out new, unused account numbers."""

    @abstractmethod
    def next_number(self) -> str:
        """Return a number that hasn't been given out before."""


class SequentialAccountNumberGenerator(AccountNumberGenerator):
    """Hands out 10000001, 10000002, 10000003 and so on."""

    def __init__(self, start: int = 10000001) -> None:
        largest = 10 ** ACCOUNT_NUMBER_LENGTH - 1
        if isinstance(start, bool) or not isinstance(start, int) or not 0 < start <= largest:
            raise ValidationError(f"Start must be a whole number from 1 to {largest}.")
        self._next = start

    def next_number(self) -> str:
        if self._next >= 10 ** ACCOUNT_NUMBER_LENGTH:
            raise ValidationError("No account numbers left.")
        number = f"{self._next:0{ACCOUNT_NUMBER_LENGTH}d}"  # pad with zeros to 8 digits
        self._next += 1
        return number
