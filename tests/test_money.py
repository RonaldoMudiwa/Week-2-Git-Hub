"""Tests for the money helpers."""

from decimal import Decimal

import pytest

from banking import ValidationError, format_money, to_money
from banking.money import positive_amount


class TestToMoney:

    @pytest.mark.parametrize("value, expected", [
        ("12.5", "12.50"),
        (12, "12.00"),
        (Decimal("0.125"), "0.13"),   # halves round up
        ("  7.1 ", "7.10"),
        ("-3", "-3.00"),
    ])
    def test_valid(self, value, expected):
        assert to_money(value) == Decimal(expected)

    @pytest.mark.parametrize("bad", [0.1, True, None, "ten", "NaN", "Infinity"])
    def test_invalid(self, bad):
        with pytest.raises(ValidationError):
            to_money(bad)


class TestPositiveAmount:

    def test_above_zero(self):
        assert positive_amount("0.01") == Decimal("0.01")

    @pytest.mark.parametrize("bad", ["0", "-1", "0.001"])
    def test_zero_or_less_is_rejected(self, bad):
        with pytest.raises(ValidationError):
            positive_amount(bad)


@pytest.mark.parametrize("amount, text", [
    (Decimal("1234.5"), "£1,234.50"),
    (Decimal("-5"), "-£5.00"),
    (Decimal("0"), "£0.00"),
])
def test_format_money(amount, text):
    assert format_money(amount) == text
