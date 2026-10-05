"""Tests for bank reports and the text formatter."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from banking import (
    Bank,
    BankReport,
    FlatMonthlyFee,
    MonthActivity,
    Statement,
    TextFormatter,
)

D = Decimal


@pytest.fixture
def bank(clock) -> Bank:
    bank = Bank("Mudiwa Bank", clock=clock)
    ronaldo = bank.add_customer("Ronaldo Mudiwa", "ronaldo@example.com")
    amara = bank.add_customer("Amara Okafor", "amara@example.com")
    bank.add_customer("Nobody Yet", "nobody@example.com")

    bank.open_account(ronaldo.customer_id, "current", "100", overdraft_limit="200",
                      fee_policy=FlatMonthlyFee("3"))
    bank.open_account(ronaldo.customer_id, "savings", "1200", interest_rate="4.5")
    bank.open_account(amara.customer_id, "current", "20", overdraft_limit="100")
    bank.open_account(amara.customer_id, "current", "0", overdraft_limit="50")

    bank.get_account("10000003").withdraw("80")   # Amara at -60
    bank.get_account("10000004").withdraw("10")   # Amara at -10
    bank.run_month_end()                          # £3 fee, £4.50 interest
    return bank


@pytest.fixture
def report(bank) -> BankReport:
    return BankReport(bank)


class TestCustomerSummaries:

    def test_richest_first(self, report):
        names = [row.customer.name for row in report.customer_summaries()]
        assert names == ["Ronaldo Mudiwa", "Nobody Yet", "Amara Okafor"]

    def test_totals(self, report):
        rows = {row.customer.name: row for row in report.customer_summaries()}
        assert rows["Ronaldo Mudiwa"].total_balance == D("1301.50")
        assert rows["Ronaldo Mudiwa"].account_count == 2
        assert rows["Amara Okafor"].total_balance == D("-70.00")

    def test_customer_with_no_accounts(self, report):
        rows = {row.customer.name: row for row in report.customer_summaries()}
        assert rows["Nobody Yet"].account_count == 0
        assert rows["Nobody Yet"].total_balance == D("0.00")


class TestTotalsByType:

    def test_rows(self, report):
        rows = {row.account_type: row for row in report.totals_by_account_type()}
        assert rows["current"].account_count == 3
        assert rows["current"].total_balance == D("27.00")
        assert rows["savings"].total_balance == D("1204.50")

    def test_adds_up_to_the_bank_total(self, bank, report):
        total = sum(row.total_balance for row in report.totals_by_account_type())
        assert total == bank.total_deposits


class TestOverdrawn:

    def test_most_overdrawn_first(self, report):
        assert [a.account_number for a in report.overdrawn_accounts()] == ["10000003", "10000004"]

    def test_none(self, clock):
        bank = Bank("Tidy Bank", clock=clock)
        customer = bank.add_customer("R", "r@example.com")
        bank.open_account(customer.customer_id, "current", "5")
        assert BankReport(bank).overdrawn_accounts() == []


class TestMonthActivity:

    def test_this_month(self, report, clock):
        activity = report.month_activity(clock.now.year, clock.now.month)
        assert activity.money_in == D("1324.50")    # deposits plus interest
        assert activity.money_out == D("93.00")     # withdrawals plus the fee
        assert activity.interest_paid == D("4.50")
        assert activity.fees_charged == D("3.00")

    def test_in_minus_out_is_the_change_in_the_bank(self, bank, report, clock):
        activity = report.month_activity(clock.now.year, clock.now.month)
        assert activity.money_in - activity.money_out == bank.total_deposits

    def test_quiet_month(self, report):
        activity = report.month_activity(2020, 1)
        assert activity.money_in == activity.money_out == D("0.00")

    def test_report_does_not_change_the_bank(self, bank, report, clock):
        before = [len(a.transactions) for a in bank]
        report.customer_summaries()
        report.month_activity(clock.now.year, clock.now.month)
        assert [len(a.transactions) for a in bank] == before


class TestTextFormatter:

    @pytest.fixture
    def formatter(self):
        return TextFormatter()

    def test_statement(self, formatter, bank, clock):
        text = formatter.statement(Statement.for_month(bank.get_account("10000001"),
                                                       clock.now.year, clock.now.month))
        assert "Statement for current account 10000001" in text
        assert "Opening balance" in text and "Closing balance" in text
        assert "Monthly fee" in text and "£97.00" in text

    def test_empty_statement(self, formatter, bank):
        statement = Statement.for_period(bank.get_account("10000001"),
                                         date(2020, 1, 1), date(2020, 1, 31))
        assert "No transactions in this period." in formatter.statement(statement)

    def test_customer_table(self, formatter, report):
        text = formatter.customer_table(report.customer_summaries())
        assert "Ronaldo Mudiwa (C0001)" in text and "£1,301.50" in text and "-£70.00" in text

    def test_type_table(self, formatter, report):
        assert "Savings" in formatter.type_table(report.totals_by_account_type())

    def test_overdrawn_table(self, formatter, report):
        assert "-£60.00" in formatter.overdrawn_table(report.overdrawn_accounts())

    def test_month_activity(self, formatter):
        activity = MonthActivity(2026, 3, D("10"), D("4"), D("1"), D("2"))
        text = formatter.month_activity(activity)
        assert text.startswith("Activity for 2026-03") and "Fees charged" in text

    @pytest.mark.parametrize("method, message", [
        ("customer_table", "No customers yet."),
        ("type_table", "No accounts yet."),
        ("overdrawn_table", "No accounts are overdrawn."),
    ])
    def test_empty_tables(self, formatter, method, message):
        assert getattr(formatter, method)([]) == message
