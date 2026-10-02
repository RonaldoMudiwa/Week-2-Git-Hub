"""Tests for applying interest and fees to accounts and the whole bank."""

from __future__ import annotations

from decimal import Decimal

import pytest

from banking import (
    Bank,
    CurrentAccount,
    FlatMonthlyFee,
    FlatRateInterest,
    NoInterest,
    OverdraftFee,
    SavingsAccount,
    TieredInterest,
    TransactionType,
    ValidationError,
)

D = Decimal


class TestAccountMonthEnd:

    def test_savings_earns_interest(self, clock):
        savings = SavingsAccount("1", "Ronaldo", "1200", interest_rate="4.5", clock=clock)
        added = savings.apply_month_end()
        assert savings.balance == D("1204.50")
        assert [t.kind for t in added] == [TransactionType.INTEREST]
        assert added[0].description == "Monthly interest"

    def test_current_pays_no_interest_by_default(self, clock):
        current = CurrentAccount("1", "Ronaldo", "1000", clock=clock)
        assert current.apply_month_end() == []
        assert current.balance == D("1000.00")

    def test_fee_is_taken(self, clock):
        current = CurrentAccount("1", "Ronaldo", "100", clock=clock, fee_policy=FlatMonthlyFee("3"))
        current.apply_month_end()
        assert current.balance == D("97.00")
        assert current.transactions[-1].kind is TransactionType.FEE

    def test_interest_comes_before_fees(self, clock):
        account = SavingsAccount("1", "Ronaldo", "1200", interest_rate="4.5", clock=clock,
                                 fee_policy=FlatMonthlyFee("1"))
        kinds = [t.kind for t in account.apply_month_end()]
        assert kinds == [TransactionType.INTEREST, TransactionType.FEE]

    def test_fee_can_go_past_the_overdraft(self, clock):
        """A bank charge is taken even if there isn't room for it."""
        current = CurrentAccount("1", "Ronaldo", "0", overdraft_limit="100", clock=clock,
                                 fee_policy=OverdraftFee("24", minimum="5"))
        current.withdraw("100")
        current.apply_month_end()
        assert current.balance == D("-105.00")

    def test_overdraft_fee_only_when_overdrawn(self, clock):
        current = CurrentAccount("1", "Ronaldo", "50", overdraft_limit="100", clock=clock,
                                 fee_policy=OverdraftFee("24", minimum="5"))
        assert current.apply_month_end() == []

    def test_fees_do_not_use_up_savings_withdrawals(self, clock):
        savings = SavingsAccount("1", "Ronaldo", "100", max_withdrawals_per_month=1,
                                 clock=clock, fee_policy=FlatMonthlyFee("1"))
        savings.apply_month_end()
        assert savings.withdrawals_this_month == 0
        savings.withdraw("10")

    def test_only_once_a_month(self, clock):
        savings = SavingsAccount("1", "Ronaldo", "1200", interest_rate="4.5", clock=clock)
        savings.apply_month_end()
        assert savings.month_end_done
        with pytest.raises(ValidationError, match="already been run"):
            savings.apply_month_end()
        assert savings.balance == D("1204.50")

    def test_runs_again_next_month(self, clock):
        savings = SavingsAccount("1", "Ronaldo", "1200", interest_rate="4.5", clock=clock)
        savings.apply_month_end()
        clock.advance(days=31)
        assert not savings.month_end_done
        savings.apply_month_end()
        assert savings.balance == D("1209.02")  # interest on the interest too

    def test_frozen_account_still_gets_interest_and_fees(self, clock):
        current = CurrentAccount("1", "Ronaldo", "100", clock=clock, fee_policy=FlatMonthlyFee("3"))
        current.freeze()
        current.apply_month_end()
        assert current.balance == D("97.00")

    def test_closed_account_is_skipped(self, clock):
        current = CurrentAccount("1", "Ronaldo", "0", clock=clock, fee_policy=FlatMonthlyFee("3"))
        current.close()
        assert current.apply_month_end() == []
        assert current.balance == D("0.00")


class TestSwappingRules:
    """The same account follows whatever rule it is given."""

    def test_change_fee_policy(self, clock):
        current = CurrentAccount("1", "Ronaldo", "100", clock=clock)
        current.fee_policy = FlatMonthlyFee("5")
        current.apply_month_end()
        assert current.balance == D("95.00")

    def test_savings_with_tiered_interest(self, clock):
        savings = SavingsAccount("1", "Ronaldo", "3000", clock=clock,
                                 interest_policy=TieredInterest([("1000", "2"), (None, "3")]))
        savings.apply_month_end()
        assert savings.balance == D("3006.67")
        assert savings.interest_rate is None  # no single rate any more

    def test_interest_rate_is_a_shortcut_for_a_flat_rate(self, clock):
        savings = SavingsAccount("1", "Ronaldo", clock=clock)
        savings.interest_rate = "3"
        assert isinstance(savings.interest_policy, FlatRateInterest)
        assert savings.interest_rate == D("3.00")

    def test_cannot_give_both_rate_and_policy(self, clock):
        with pytest.raises(ValidationError, match="not both"):
            SavingsAccount("1", "Ronaldo", interest_rate="3", clock=clock,
                           interest_policy=NoInterest())

    def test_policy_must_be_the_right_kind(self, clock):
        current = CurrentAccount("1", "Ronaldo", clock=clock)
        with pytest.raises(ValidationError):
            current.fee_policy = NoInterest()
        with pytest.raises(ValidationError):
            current.interest_policy = FlatMonthlyFee("1")
        with pytest.raises(ValidationError):
            current.fee_policy = "£3"


class TestBankMonthEnd:

    @pytest.fixture
    def bank(self, clock):
        bank = Bank("Mudiwa Bank", clock=clock)
        ronaldo = bank.add_customer("Ronaldo", "ronaldo@example.com")
        bank.open_account(ronaldo.customer_id, "current", "100", fee_policy=FlatMonthlyFee("3"))
        bank.open_account(ronaldo.customer_id, "savings", "1200", interest_rate="4.5")
        bank.open_account(ronaldo.customer_id, "current", "50")  # no rules, nothing happens
        return bank

    def test_every_account_follows_its_own_rules(self, bank):
        changes = bank.run_month_end()
        assert set(changes) == {"10000001", "10000002"}
        assert bank.get_account("10000001").balance == D("97.00")
        assert bank.get_account("10000002").balance == D("1204.50")
        assert bank.get_account("10000003").balance == D("50.00")

    def test_running_twice_does_no_harm(self, bank):
        bank.run_month_end()
        assert bank.run_month_end() == {}
        assert bank.get_account("10000001").balance == D("97.00")

    def test_policies_can_be_set_when_opening(self, bank):
        account = bank.open_account("C0001", "current", "0", overdraft_limit="100",
                                    fee_policy=OverdraftFee("24"))
        assert isinstance(account.fee_policy, OverdraftFee)

    def test_closed_accounts_are_skipped(self, bank):
        bank.get_account("10000003").withdraw("50")
        bank.close_account("10000003")
        bank.get_account("10000003").fee_policy = FlatMonthlyFee("3")
        assert "10000003" not in bank.run_month_end()
