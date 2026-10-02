"""An account for saving, which earns interest."""

from __future__ import annotations

from decimal import Decimal

from .account import Account, Clock
from .enums import TransactionType
from .exceptions import ValidationError, WithdrawalLimitError
from .money import ZERO, to_money
from .policies import FeePolicy, FlatRateInterest, InterestPolicy

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
        *,
        interest_policy: InterestPolicy | None = None,
        fee_policy: FeePolicy | None = None,
    ) -> None:
        """
        Pass interest_rate for a simple flat rate, or interest_policy for
        anything else, such as tiered rates. Not both.
        """
        super().__init__(account_number, owner_name, opening_balance, clock,
                         interest_policy=interest_policy, fee_policy=fee_policy)
        if interest_policy is None:
            self.interest_rate = interest_rate
        elif to_money(interest_rate) != ZERO:
            raise ValidationError("Give either interest_rate or interest_policy, not both.")
        self.max_withdrawals_per_month = max_withdrawals_per_month

    @property
    def interest_rate(self) -> Decimal | None:
        """Yearly interest as a percentage, e.g. Decimal("4.50").

        None if the account uses a policy without one single rate, such as
        tiered interest.
        """
        if isinstance(self.interest_policy, FlatRateInterest):
            return self.interest_policy.yearly_rate
        return None

    @interest_rate.setter
    def interest_rate(self, value: Decimal | int | str) -> None:
        """A shortcut that switches the account to a flat rate."""
        rate = to_money(value)
        if not ZERO <= rate <= MAX_INTEREST_RATE:
            raise ValidationError(f"Interest rate must be between 0 and {MAX_INTEREST_RATE}%.")
        self.interest_policy = FlatRateInterest(rate)

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
        if self.withdrawals_this_month >= self._max_withdrawals:
            plural = "" if self._max_withdrawals == 1 else "s"
            raise WithdrawalLimitError(
                f"Only {self._max_withdrawals} withdrawal{plural} allowed each month."
            )
        super()._check_withdrawal(amount, kind)
