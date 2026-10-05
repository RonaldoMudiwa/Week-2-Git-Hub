"""Reports about the whole bank, and turning reports into text.

BankReport works out the numbers and returns plain data. TextFormatter
turns that data, or a Statement, into text. Keeping the two apart means a
web page or a spreadsheet could later use the same numbers.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .account import Account
from .bank import Bank
from .customer import Customer
from .money import ZERO, format_money
from .statements import Statement


@dataclass(frozen=True)
class CustomerSummary:
    """How much one customer holds across all their accounts."""

    customer: Customer
    account_count: int
    total_balance: Decimal


@dataclass(frozen=True)
class TypeSummary:
    """How many accounts of one type there are, and how much they hold."""

    account_type: str
    account_count: int
    total_balance: Decimal


@dataclass(frozen=True)
class MonthActivity:
    """Money that moved across the whole bank in one month."""

    year: int
    month: int
    money_in: Decimal
    money_out: Decimal
    interest_paid: Decimal
    fees_charged: Decimal


class BankReport:
    """Answers questions about a bank. Never changes it."""

    def __init__(self, bank: Bank) -> None:
        self._bank = bank

    def customer_summaries(self) -> list[CustomerSummary]:
        """One row per customer, richest first."""
        rows = []
        for customer in self._bank.customers:
            accounts = self._bank.accounts_for(customer.customer_id)
            total = sum((a.balance for a in accounts), start=ZERO)
            rows.append(CustomerSummary(customer, len(accounts), total))
        return sorted(rows, key=lambda row: row.total_balance, reverse=True)

    def totals_by_account_type(self) -> list[TypeSummary]:
        """One row per account type, e.g. current and savings."""
        counts: dict[str, int] = defaultdict(int)
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for account in self._bank:
            counts[account.ACCOUNT_TYPE] += 1
            totals[account.ACCOUNT_TYPE] += account.balance
        return [TypeSummary(kind, counts[kind], totals[kind]) for kind in sorted(counts)]

    def overdrawn_accounts(self) -> list[Account]:
        """Accounts below zero, most overdrawn first."""
        return sorted((a for a in self._bank if a.balance < ZERO), key=lambda a: a.balance)

    def month_activity(self, year: int, month: int) -> MonthActivity:
        """Totals for one month across every account, using their statements."""
        statements = [Statement.for_month(account, year, month) for account in self._bank]
        return MonthActivity(
            year,
            month,
            money_in=sum((s.money_in for s in statements), start=ZERO),
            money_out=sum((s.money_out for s in statements), start=ZERO),
            interest_paid=sum((s.interest_paid for s in statements), start=ZERO),
            fees_charged=sum((s.fees_charged for s in statements), start=ZERO),
        )


class TextFormatter:
    """Turns statements and reports into plain text for the terminal."""

    WIDTH = 74

    def statement(self, statement: Statement) -> str:
        line = "-" * self.WIDTH
        rows = [
            f"Statement for {statement.account_type} account {statement.account_number}",
            f"{statement.owner_name}, {statement.start} to {statement.end}",
            line,
            f"{'Opening balance':<52}{format_money(statement.opening_balance):>22}",
        ]
        if statement.lines:
            rows.extend(t.summary_line() for t in statement.lines)
        else:
            rows.append("No transactions in this period.")
        rows += [
            line,
            f"{'Money in':<52}{format_money(statement.money_in):>22}",
            f"{'Money out':<52}{format_money(statement.money_out):>22}",
            f"{'Closing balance':<52}{format_money(statement.closing_balance):>22}",
        ]
        return "\n".join(rows)

    def customer_table(self, rows: list[CustomerSummary]) -> str:
        if not rows:
            return "No customers yet."
        lines = [f"{'Customer':<30}{'Accounts':>10}{'Total':>16}", "-" * 56]
        for row in rows:
            lines.append(f"{str(row.customer):<30}{row.account_count:>10}"
                         f"{format_money(row.total_balance):>16}")
        return "\n".join(lines)

    def type_table(self, rows: list[TypeSummary]) -> str:
        if not rows:
            return "No accounts yet."
        lines = [f"{'Account type':<20}{'Accounts':>10}{'Total':>16}", "-" * 46]
        for row in rows:
            lines.append(f"{row.account_type.title():<20}{row.account_count:>10}"
                         f"{format_money(row.total_balance):>16}")
        return "\n".join(lines)

    def overdrawn_table(self, accounts: list[Account]) -> str:
        if not accounts:
            return "No accounts are overdrawn."
        lines = [f"{'Account':<12}{'Owner':<26}{'Balance':>14}", "-" * 52]
        for account in accounts:
            lines.append(f"{account.account_number:<12}{account.owner_name:<26}"
                         f"{format_money(account.balance):>14}")
        return "\n".join(lines)

    def month_activity(self, activity: MonthActivity) -> str:
        rows = [
            ("Money in", activity.money_in),
            ("Money out", activity.money_out),
            ("Interest paid to customers", activity.interest_paid),
            ("Fees charged", activity.fees_charged),
        ]
        lines = [f"Activity for {activity.year}-{activity.month:02d}", "-" * 46]
        lines += [f"{label:<30}{format_money(amount):>16}" for label, amount in rows]
        return "\n".join(lines)
