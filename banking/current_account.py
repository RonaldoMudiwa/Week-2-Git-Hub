"""An everyday account that can have an overdraft."""

from __future__ import annotations

from decimal import Decimal

from .account import Account, Clock
from .exceptions import ValidationError
from .money import ZERO, format_money, to_money
from .policies import FeePolicy, InterestPolicy


class CurrentAccount(Account):
    """An account for day to day spending.

    The overdraft lets the balance go below zero, down to minus the limit.

        >>> account = CurrentAccount("10000001", "Ronaldo", "50", overdraft_limit="100")
        >>> account.available_to_withdraw
        Decimal('150.00')
    """

    ACCOUNT_TYPE = "current"

    def __init__(
        self,
        account_number: str,
        owner_name: str,
        opening_balance: Decimal | int | str = "0",
        overdraft_limit: Decimal | int | str = "0",
        clock: Clock | None = None,
        *,
        interest_policy: InterestPolicy | None = None,
        fee_policy: FeePolicy | None = None,
    ) -> None:
        # Set before super(), because the parent may make the opening
        # deposit, and anything that reads the overdraft must find it there.
        self._overdraft_limit = ZERO
        super().__init__(account_number, owner_name, opening_balance, clock,
                         interest_policy=interest_policy, fee_policy=fee_policy)
        self.overdraft_limit = overdraft_limit

    @property
    def overdraft_limit(self) -> Decimal:
        """How far below zero the balance is allowed to go."""
        return self._overdraft_limit

    @overdraft_limit.setter
    def overdraft_limit(self, value: Decimal | int | str) -> None:
        limit = to_money(value)
        if limit < ZERO:
            raise ValidationError("Overdraft limit can't be negative.")
        # Can't shrink the limit below what is already borrowed.
        if self.balance < -limit:
            raise ValidationError(
                f"The account is already overdrawn by {format_money(-self.balance)}, "
                f"so the limit can't go below that."
            )
        self._overdraft_limit = limit

    @property
    def available_to_withdraw(self) -> Decimal:
        """The balance plus whatever overdraft is left."""
        return self.balance + self._overdraft_limit

    @property
    def is_overdrawn(self) -> bool:
        return self.balance < ZERO
