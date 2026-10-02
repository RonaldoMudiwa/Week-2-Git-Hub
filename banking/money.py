"""Helpers for amounts of money.

Money is always a Decimal, never a float, because 0.1 + 0.2 as floats
gives 0.30000000000000004.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .exceptions import ValidationError

PENNY = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value: Decimal | int | str) -> Decimal:
    """Turn "12.5", 12 or Decimal("12.5") into Decimal("12.50").

    Raises:
        ValidationError: If it isn't a number, or is a float or True/False.
    """
    # True counts as 1 in Python, and floats aren't exact enough for money.
    if isinstance(value, (bool, float)):
        raise ValidationError("Use text, a whole number or Decimal for money, not a float.")
    if value is None:
        raise ValidationError("An amount is required.")
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation as error:
        raise ValidationError(f"{value!r} is not a valid amount.") from error
    if not amount.is_finite():
        raise ValidationError("Amount must be a real number.")
    # Round halves up, like a shop would.
    return amount.quantize(PENNY, rounding=ROUND_HALF_UP)


def positive_amount(value: Decimal | int | str) -> Decimal:
    """Like to_money, but the amount must be above zero."""
    amount = to_money(value)
    if amount <= ZERO:
        raise ValidationError(f"Amount must be greater than zero, got {amount}.")
    return amount


def format_money(amount: Decimal) -> str:
    """£1,234.56, or -£5.00 for a negative amount."""
    sign = "-" if amount < 0 else ""
    return f"{sign}£{abs(amount):,.2f}"
