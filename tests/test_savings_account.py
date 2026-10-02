"""Tests for what's special about a savings account."""

from decimal import Decimal

import pytest

from banking import (
    InsufficientFundsError,
    SavingsAccount,
    ValidationError,
    WithdrawalLimitError,
)


@pytest.fixture
def savings(clock) -> SavingsAccount:
    return SavingsAccount("10000002", "Ronaldo", "500", interest_rate="4.5",
                          max_withdrawals_per_month=2, clock=clock)


class TestNoOverdraft:

    def test_available_is_the_balance(self, savings):
        assert savings.available_to_withdraw == Decimal("500.00")

    def test_cannot_go_below_zero(self, savings):
        with pytest.raises(InsufficientFundsError):
            savings.withdraw("500.01")


class TestMonthlyLimit:

    def test_counts_withdrawals(self, savings):
        savings.withdraw("10")
        assert savings.withdrawals_this_month == 1

    def test_deposits_do_not_count(self, savings):
        savings.deposit("10")
        assert savings.withdrawals_this_month == 0

    def test_limit_is_enforced(self, savings):
        savings.withdraw("10")
        savings.withdraw("10")
        with pytest.raises(WithdrawalLimitError):
            savings.withdraw("10")
        assert savings.balance == Decimal("480.00")

    def test_resets_next_month(self, savings, clock):
        savings.withdraw("10")
        savings.withdraw("10")
        clock.advance(days=31)
        savings.withdraw("10")
        assert savings.withdrawals_this_month == 1

    def test_limit_is_checked_before_money(self, savings):
        """Over the limit, the reason given is the limit, not the money."""
        savings.withdraw("10")
        savings.withdraw("10")
        with pytest.raises(WithdrawalLimitError):
            savings.withdraw("100000")

    def test_failed_withdrawal_does_not_use_up_the_limit(self, savings):
        with pytest.raises(InsufficientFundsError):
            savings.withdraw("100000")
        assert savings.withdrawals_this_month == 0

    def test_default_limit_is_three(self, clock):
        assert SavingsAccount("1", "Ronaldo", clock=clock).max_withdrawals_per_month == 3

    @pytest.mark.parametrize("bad", [0, -1, 2.5, True, "3"])
    def test_bad_limit(self, clock, bad):
        with pytest.raises(ValidationError):
            SavingsAccount("1", "Ronaldo", max_withdrawals_per_month=bad, clock=clock)


class TestInterestRate:

    def test_stored_as_decimal(self, savings):
        assert savings.interest_rate == Decimal("4.50")

    def test_zero_by_default(self, clock):
        assert SavingsAccount("1", "Ronaldo", clock=clock).interest_rate == Decimal("0.00")

    @pytest.mark.parametrize("bad", ["-0.5", "20.01", "lots"])
    def test_bad_rate(self, savings, bad):
        with pytest.raises(ValidationError):
            savings.interest_rate = bad
