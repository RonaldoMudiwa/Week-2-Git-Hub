"""An account for saving, which earns interest."""

from __future__ import annotations

from decimal import Decimal

from .account import Account, Clock
from .enums import TransactionType
from .exceptions import ValidationError, WithdrawalLimitError
from .money import ZERO, to_money

# Interest is given as a yearly percentage, e.g. "4.5" means 4.5%.
MAX_INTEREST_RATE = Decimal("20")


class SavingsAccount(Account):
    """An account that can't go below zero and limits withdrawals.

    Taking money out too often defeats the point of saving, so only a set
    number of withdrawals are allowed each calendar month.

        >>> savings = SavingsAccount("10000002", "Ronaldo", "500", interest_rate="4.5")
        >>> savings.available_to_withdraw
        Decimal('500.00')
    """

    ACCOUNT_TYPE = "savings"

    def __init__(
        self,
        account_number: str,
        owner_name: str,
        opening_balance: Decimal | int | str = "0",
        interest_rate: Decimal | int | str = "0",
        max_withdrawals_per_month: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(account_number, owner_name, opening_balance, clock)
        self.interest_rate = interest_rate
        self.max_withdrawals_per_month = max_withdrawals_per_month

    @property
    def interest_rate(self) -> Decimal:
        """Yearly interest as a percentage, e.g. Decimal("4.50")."""
        return self._interest_rate

    @interest_rate.setter
    def interest_rate(self, value: Decimal | int | str) -> None:
        rate = to_money(value)
        if not ZERO <= rate <= MAX_INTEREST_RATE:
            raise ValidationError(f"Interest rate must be between 0 and {MAX_INTEREST_RATE}%.")
        self._interest_rate = rate

    @property
    def max_withdrawals_per_month(self) -> int:
        return self._max_withdrawals

    @max_withdrawals_per_month.setter
    def max_withdrawals_per_month(self, value: int) -> None:
        # bool is a kind of int in Python, so it's ruled out by name.
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError("Withdrawals per month must be a whole number of at least 1.")
        self._max_withdrawals = value

    @property
    def available_to_withdraw(self) -> Decimal:
        """No overdraft, so it's just the balance."""
        return max(self.balance, ZERO)

    @property
    def withdrawals_this_month(self) -> int:
        """How many times money has been taken out this calendar month."""
        now = self._clock()
        return sum(
            1 for t in self._transactions
            if not t.kind.is_credit
            and t.kind is not TransactionType.FEE  # bank charges don't count
            and (t.timestamp.year, t.timestamp.month) == (now.year, now.month)
        )

    def _check_withdrawal(self, amount: Decimal, kind: TransactionType) -> None:
        """Add the monthly limit on top of the normal money check."""
        if kind is not TransactionType.FEE and \
                self.withdrawals_this_month >= self._max_withdrawals:
            raise WithdrawalLimitError(
                f"Only {self._max_withdrawals} withdrawals are allowed each month."
            )
        super()._check_withdrawal(amount, kind)
