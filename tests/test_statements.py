"""Tests for bank statements."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from banking import (
    CurrentAccount,
    FlatMonthlyFee,
    SavingsAccount,
    Statement,
    ValidationError,
)

from .conftest import FakeClock

D = Decimal


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 10, 9, 0))


@pytest.fixture
def account(clock) -> CurrentAccount:
    """Activity across September and October."""
    account = CurrentAccount("10000001", "Ronaldo", "500", overdraft_limit="100",
                             clock=clock, fee_policy=FlatMonthlyFee("3"))
    account.withdraw("120", "Groceries")              # 10 Sep
    clock.advance(days=20)
    account.apply_month_end()                         # 30 Sep, £3 fee
    clock.advance(days=2)
    account.deposit("1800", "Wages")                  # 2 Oct
    clock.advance(days=5)
    account.withdraw("950", "Rent")                   # 7 Oct
    return account


class TestForMonth:

    def test_september(self, account):
        statement = Statement.for_month(account, 2026, 9)
        assert statement.opening_balance == D("0.00")
        assert [t.description for t in statement.lines] == ["Opening deposit", "Groceries",
                                                            "Monthly fee"]
        assert statement.closing_balance == D("377.00")

    def test_october_opens_where_september_closed(self, account):
        september = Statement.for_month(account, 2026, 9)
        october = Statement.for_month(account, 2026, 10)
        assert october.opening_balance == september.closing_balance
        assert october.closing_balance == account.balance == D("1227.00")

    def test_totals(self, account):
        september = Statement.for_month(account, 2026, 9)
        assert september.money_in == D("500.00")
        assert september.money_out == D("123.00")
        assert september.fees_charged == D("3.00")
        assert september.interest_paid == D("0.00")

    def test_quiet_month(self, account):
        november = Statement.for_month(account, 2026, 11)
        assert november.lines == ()
        assert november.opening_balance == november.closing_balance == account.balance

    def test_before_the_account_existed(self, account):
        august = Statement.for_month(account, 2026, 8)
        assert august.opening_balance == august.closing_balance == D("0.00")

    def test_dates_cover_the_whole_month(self, account):
        february = Statement.for_month(account, 2028, 2)  # a leap year
        assert (february.start, february.end) == (date(2028, 2, 1), date(2028, 2, 29))

    @pytest.mark.parametrize("bad", [0, 13])
    def test_bad_month(self, account, bad):
        with pytest.raises(ValidationError):
            Statement.for_month(account, 2026, bad)


class TestForPeriod:

    def test_both_days_included(self, account):
        statement = Statement.for_period(account, date(2026, 9, 30), date(2026, 10, 2))
        assert [t.description for t in statement.lines] == ["Monthly fee", "Wages"]

    def test_start_after_end(self, account):
        with pytest.raises(ValidationError):
            Statement.for_period(account, date(2026, 10, 2), date(2026, 9, 30))

    def test_needs_real_dates(self, account):
        with pytest.raises(ValidationError):
            Statement.for_period(account, "2026-09-01", date(2026, 9, 30))

    def test_whole_history_matches_the_account(self, account):
        statement = Statement.for_period(account, date(2000, 1, 1), date(2100, 1, 1))
        assert statement.lines == account.transactions
        assert statement.closing_balance == account.balance


class TestDetails:

    def test_records_the_account(self, account):
        statement = Statement.for_month(account, 2026, 9)
        assert (statement.account_number, statement.owner_name, statement.account_type) == \
            ("10000001", "Ronaldo", "current")

    def test_cannot_be_changed(self, account):
        statement = Statement.for_month(account, 2026, 9)
        with pytest.raises(AttributeError):
            statement.opening_balance = D("1000000")

    def test_later_activity_does_not_change_an_old_statement(self, account):
        september = Statement.for_month(account, 2026, 9)
        account.deposit("5")
        assert september.closing_balance == D("377.00")

    def test_interest_shows_up(self, clock):
        savings = SavingsAccount("2", "Ronaldo", "1200", interest_rate="4.5", clock=clock)
        savings.apply_month_end()
        assert Statement.for_month(savings, 2026, 9).interest_paid == D("4.50")
