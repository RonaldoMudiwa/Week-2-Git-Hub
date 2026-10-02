"""Tests for what's special about a current account: the overdraft."""

from decimal import Decimal

import pytest

from banking import CurrentAccount, InsufficientFundsError, ValidationError


@pytest.fixture
def account(clock) -> CurrentAccount:
    return CurrentAccount("10000001", "Ronaldo", "50", overdraft_limit="100", clock=clock)


class TestOverdraft:

    def test_available_includes_overdraft(self, account):
        assert account.available_to_withdraw == Decimal("150.00")

    def test_can_go_below_zero(self, account):
        account.withdraw("120")
        assert account.balance == Decimal("-70.00")
        assert account.is_overdrawn

    def test_cannot_pass_the_limit(self, account):
        with pytest.raises(InsufficientFundsError):
            account.withdraw("150.01")

    def test_exactly_the_limit_is_fine(self, account):
        account.withdraw("150")
        assert account.available_to_withdraw == Decimal("0.00")

    def test_no_overdraft_by_default(self, clock):
        account = CurrentAccount("1", "Ronaldo", "10", clock=clock)
        with pytest.raises(InsufficientFundsError):
            account.withdraw("10.01")

    def test_not_overdrawn_at_zero(self, account):
        account.withdraw("50")
        assert not account.is_overdrawn

    def test_limit_can_be_raised(self, account):
        account.overdraft_limit = "500"
        assert account.available_to_withdraw == Decimal("550.00")

    def test_negative_limit(self, account):
        with pytest.raises(ValidationError):
            account.overdraft_limit = "-1"

    def test_limit_cannot_drop_below_what_is_owed(self, account):
        account.withdraw("130")  # now at -80
        with pytest.raises(ValidationError, match="overdrawn by £80.00"):
            account.overdraft_limit = "50"
        account.overdraft_limit = "80"
        assert account.overdraft_limit == Decimal("80.00")

    def test_close_while_overdrawn(self, account):
        account.withdraw("100")
        with pytest.raises(ValidationError):
            account.close()
