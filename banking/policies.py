"""Rules for monthly interest and fees.

Each rule is a small object an account carries around, like a card with
the bank's terms printed on it. Swap the card and the account follows the
new terms, without any change to the account's own code.

Interest and fees are kept as two separate kinds of rule, so a class only
has to provide the one method it actually needs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal

from .exceptions import ValidationError
from .money import PENNY, ZERO, to_money

MONTHS_IN_YEAR = 12
MAX_RATE = Decimal("100")


def _rate(value: Decimal | int | str, name: str) -> Decimal:
    """Check a yearly percentage rate, e.g. "4.5" for 4.5%."""
    rate = to_money(value)
    if not ZERO <= rate <= MAX_RATE:
        raise ValidationError(f"{name} must be between 0 and {MAX_RATE}%.")
    return rate


def _monthly_share(amount: Decimal, yearly_rate: Decimal) -> Decimal:
    """One month's worth of a yearly percentage of an amount, to the penny."""
    return (amount * yearly_rate / 100 / MONTHS_IN_YEAR).quantize(PENNY, rounding=ROUND_HALF_UP)


# ----------------------------------------------------------------------
# Interest
# ----------------------------------------------------------------------


class InterestPolicy(ABC):
    """Works out how much interest to pay an account each month."""

    @abstractmethod
    def monthly_interest(self, balance: Decimal) -> Decimal:
        """Interest for one month on this balance. Never negative."""


class NoInterest(InterestPolicy):
    """Pays nothing. The default for a current account."""

    def monthly_interest(self, balance: Decimal) -> Decimal:
        return ZERO

    def __repr__(self) -> str:
        return "NoInterest()"


class FlatRateInterest(InterestPolicy):
    """The same yearly rate on the whole balance.

        >>> FlatRateInterest("4.8").monthly_interest(Decimal("1000"))
        Decimal('4.00')
    """

    def __init__(self, yearly_rate: Decimal | int | str) -> None:
        self._rate = _rate(yearly_rate, "Interest rate")

    @property
    def yearly_rate(self) -> Decimal:
        return self._rate

    def monthly_interest(self, balance: Decimal) -> Decimal:
        # No interest on money that isn't there.
        if balance <= ZERO:
            return ZERO
        return _monthly_share(balance, self._rate)

    def __repr__(self) -> str:
        return f"FlatRateInterest({str(self._rate)!r})"


class TieredInterest(InterestPolicy):
    """Different rates for different slices of the balance.

    Like income tax bands, each rate only applies to the money inside its
    band. With bands [("1000", "2"), (None, "4")], the first £1,000 earns
    2% and everything above that earns 4%. None means "no upper limit".

        >>> TieredInterest([("1000", "2"), (None, "4")]).monthly_interest(Decimal("4000"))
        Decimal('11.67')
    """

    def __init__(self, bands: list[tuple[Decimal | int | str | None, Decimal | int | str]]) -> None:
        if not bands:
            raise ValidationError("Give at least one interest band.")

        self._bands: list[tuple[Decimal | None, Decimal]] = []
        previous_top = ZERO
        for position, (top, rate) in enumerate(bands):
            is_last = position == len(bands) - 1
            if top is None:
                if not is_last:
                    raise ValidationError("Only the last band can have no upper limit.")
                limit = None
            else:
                limit = to_money(top)
                if limit <= previous_top:
                    raise ValidationError("Each band's upper limit must be higher than the one before.")
                previous_top = limit
            self._bands.append((limit, _rate(rate, "Interest rate")))

    def monthly_interest(self, balance: Decimal) -> Decimal:
        if balance <= ZERO:
            return ZERO

        total = ZERO
        bottom = ZERO
        for top, rate in self._bands:
            if balance <= bottom:
                break
            # The part of the balance that falls inside this band.
            slice_top = balance if top is None else min(balance, top)
            total += (slice_top - bottom) * rate / 100 / MONTHS_IN_YEAR
            if top is None:
                break
            bottom = top
        return total.quantize(PENNY, rounding=ROUND_HALF_UP)

    def __repr__(self) -> str:
        bands = ", ".join(f"({None if t is None else str(t)!r}, {str(r)!r})" for t, r in self._bands)
        return f"TieredInterest([{bands}])"


# ----------------------------------------------------------------------
# Fees
# ----------------------------------------------------------------------


class FeePolicy(ABC):
    """Works out what to charge an account each month."""

    @abstractmethod
    def monthly_fee(self, balance: Decimal) -> Decimal:
        """The fee for one month at this balance. Never negative."""


class NoFee(FeePolicy):
    """Charges nothing. The default for every account."""

    def monthly_fee(self, balance: Decimal) -> Decimal:
        return ZERO

    def __repr__(self) -> str:
        return "NoFee()"


class FlatMonthlyFee(FeePolicy):
    """The same charge every month, e.g. £3 for a packaged account."""

    def __init__(self, amount: Decimal | int | str) -> None:
        fee = to_money(amount)
        if fee < ZERO:
            raise ValidationError("A fee can't be negative.")
        self._amount = fee

    def monthly_fee(self, balance: Decimal) -> Decimal:
        return self._amount

    def __repr__(self) -> str:
        return f"FlatMonthlyFee({str(self._amount)!r})"


class OverdraftFee(FeePolicy):
    """Charges interest on money borrowed through the overdraft.

    Only charged when the balance is below zero. A minimum charge can be
    set, so a tiny overdraft still costs something.

        >>> OverdraftFee("24", minimum="2").monthly_fee(Decimal("-500"))
        Decimal('10.00')
    """

    def __init__(self, yearly_rate: Decimal | int | str,
                 minimum: Decimal | int | str = "0") -> None:
        self._rate = _rate(yearly_rate, "Overdraft rate")
        self._minimum = to_money(minimum)
        if self._minimum < ZERO:
            raise ValidationError("Minimum charge can't be negative.")

    def monthly_fee(self, balance: Decimal) -> Decimal:
        if balance >= ZERO:
            return ZERO
        return max(_monthly_share(-balance, self._rate), self._minimum)

    def __repr__(self) -> str:
        return f"OverdraftFee({str(self._rate)!r}, minimum={str(self._minimum)!r})"


class CombinedFees(FeePolicy):
    """Several fee rules added together, e.g. a flat fee plus overdraft charges.

    It is itself a FeePolicy, so an account can't tell the difference between
    one rule and a bundle of them.
    """

    def __init__(self, *policies: FeePolicy) -> None:
        if not policies or not all(isinstance(p, FeePolicy) for p in policies):
            raise ValidationError("CombinedFees needs one or more fee policies.")
        self._policies = policies

    def monthly_fee(self, balance: Decimal) -> Decimal:
        return sum((p.monthly_fee(balance) for p in self._policies), start=ZERO)

    def __repr__(self) -> str:
        return f"CombinedFees({', '.join(repr(p) for p in self._policies)})"

