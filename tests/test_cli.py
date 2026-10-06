"""Tests for the command line interface.

The bank is kept in memory between commands, so no real file is touched.
"""

from __future__ import annotations

import argparse
import io
import json
from decimal import Decimal

import pytest

from banking import FlatMonthlyFee, InMemoryBankRepository, JSONBankRepository
from banking.cli import BankCLI, Command, Session, default_commands, parse_month

D = Decimal


class SpyRepository(InMemoryBankRepository):
    """Counts how many times the bank was saved."""

    def __init__(self, clock) -> None:
        super().__init__(clock=clock)
        self.saves = 0

    def save(self, bank) -> None:
        self.saves += 1
        super().save(bank)


class Terminal:
    """Runs commands one after another, like typing them in a real terminal."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self.repository = SpyRepository(clock)
        self.paths = []

    def open_repository(self, path):
        self.paths.append(path)
        return self.repository

    def run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        cli = BankCLI(self.open_repository, clock=self.clock, out=out, err=err)
        code = cli.run(list(argv))
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv: str) -> str:
        """Run a command that should work and return what it printed."""
        code, out, err = self.run(*argv)
        assert code == 0, err
        assert err == ""
        return out

    def fails(self, *argv: str) -> str:
        """Run a command that should be refused and return the error text."""
        code, out, err = self.run(*argv)
        assert code == 1
        assert err.startswith("Error: ")
        return err

    @property
    def bank(self):
        return self.repository.load()


@pytest.fixture
def terminal(clock) -> Terminal:
    return Terminal(clock)


@pytest.fixture
def ready(terminal) -> Terminal:
    """One customer with a current account (10000001) and a savings account (10000002)."""
    terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
    terminal.ok("open", "C0001", "current", "--deposit", "250", "--overdraft", "200")
    terminal.ok("open", "C0001", "savings", "--deposit", "1000", "--rate", "4.5")
    terminal.repository.saves = 0
    return terminal


class TestCustomers:
    def test_add_customer_is_saved(self, terminal):
        out = terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
        assert "Ronaldo Mudiwa (C0001)" in out
        assert terminal.bank.get_customer("C0001").email == "ronaldo@example.com"

    def test_first_run_makes_a_new_bank(self, terminal):
        terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
        assert terminal.bank.name == "Mudiwa Bank"

    def test_duplicate_email_is_refused(self, terminal):
        terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
        err = terminal.fails("add-customer", "Ron", "RONALDO@example.com")
        assert "already exists" in err
        assert len(terminal.bank.customers) == 1

    def test_list_customers(self, terminal):
        assert "No customers yet." in terminal.ok("customers")
        terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
        terminal.ok("add-customer", "Amara Okafor", "amara@example.com")
        out = terminal.ok("customers")
        assert "C0001" in out and "C0002" in out
        assert "amara@example.com" in out


class TestOpeningAccounts:
    def test_current_account_options(self, ready):
        account = ready.bank.get_account("10000001")
        assert account.balance == D("250.00")
        assert account.overdraft_limit == D("200.00")

    def test_savings_account_options(self, terminal):
        terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
        out = terminal.ok("open", "C0001", "savings", "--rate", "3", "--max-withdrawals", "1")
        assert "Savings account 10000001" in out
        account = terminal.bank.get_account("10000001")
        assert account.interest_rate == D("3.00")
        assert account.max_withdrawals_per_month == 1

    def test_monthly_fee_option(self, terminal):
        terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
        terminal.ok("open", "C0001", "current", "--deposit", "10", "--monthly-fee", "3")
        assert isinstance(terminal.bank.get_account("10000001").fee_policy, FlatMonthlyFee)

    def test_option_from_the_wrong_account_type_is_refused(self, ready):
        err = ready.fails("open", "C0001", "savings", "--overdraft", "100")
        assert "savings" in err
        assert len(ready.bank) == 2

    def test_unknown_type_is_refused(self, ready):
        assert "Unknown account type" in ready.fails("open", "C0001", "crypto")

    def test_unknown_customer_is_refused(self, ready):
        assert "C0099" in ready.fails("open", "C0099", "current")

    def test_list_every_account(self, ready):
        out = ready.ok("accounts")
        assert "10000001" in out and "10000002" in out
        assert "£1,000.00" in out

    def test_list_one_customers_accounts(self, ready):
        ready.ok("add-customer", "Amara Okafor", "amara@example.com")
        ready.ok("open", "C0002", "current")
        out = ready.ok("accounts", "C0002")
        assert "10000003" in out
        assert "10000001" not in out

    def test_list_when_there_are_none(self, terminal):
        assert "No accounts yet." in terminal.ok("accounts")


class TestMovingMoney:
    def test_deposit(self, ready):
        out = ready.ok("deposit", "10000001", "50", "--note", "Birthday money")
        assert "Balance is now £300.00" in out
        account = ready.bank.get_account("10000001")
        assert account.balance == D("300.00")
        assert account.transactions[-1].description == "Birthday money"

    def test_withdraw_into_the_overdraft(self, ready):
        out = ready.ok("withdraw", "10000001", "300")
        assert "Balance is now -£50.00" in out
        assert ready.bank.get_account("10000001").balance == D("-50.00")

    def test_withdraw_too_much_changes_nothing(self, ready):
        err = ready.fails("withdraw", "10000001", "451")
        assert "available" in err
        assert ready.bank.get_account("10000001").balance == D("250.00")
        assert ready.repository.saves == 0

    def test_bad_amount_is_refused(self, ready):
        assert "not a valid amount" in ready.fails("deposit", "10000001", "ten")
        assert "greater than zero" in ready.fails("deposit", "10000001", "-5")

    def test_transfer(self, ready):
        out = ready.ok("transfer", "10000001", "10000002", "100", "--note", "Saving")
        assert "Moved £100.00 from 10000001 to 10000002" in out
        bank = ready.bank
        assert bank.get_account("10000001").balance == D("150.00")
        assert bank.get_account("10000002").balance == D("1100.00")
        assert bank.get_account("10000002").transactions[-1].description == "Saving"

    def test_transfer_to_a_missing_account(self, ready):
        assert "99999999" in ready.fails("transfer", "10000001", "99999999", "5")
        assert ready.bank.get_account("10000001").balance == D("250.00")


class TestMonthEnd:
    def test_pays_interest_and_takes_fees(self, ready):
        ready.ok("add-customer", "Amara Okafor", "amara@example.com")
        ready.ok("open", "C0002", "current", "--deposit", "20", "--monthly-fee", "3")
        out = ready.ok("month-end")
        assert "Monthly interest" in out
        assert "Monthly fee" in out
        assert "2 account(s) changed" in out
        assert ready.bank.get_account("10000003").balance == D("17.00")

    def test_second_run_in_the_same_month_does_nothing(self, ready):
        ready.ok("month-end")
        balance = ready.bank.get_account("10000002").balance
        assert "Nothing to pay or charge" in ready.ok("month-end")
        assert ready.bank.get_account("10000002").balance == balance

    def test_runs_again_next_month(self, ready):
        ready.ok("month-end")
        ready.clock.advance(days=31)
        assert "Monthly interest" in ready.ok("month-end")


class TestStatementsAndReports:
    def test_statement_for_this_month(self, ready):
        ready.ok("deposit", "10000001", "50", "--note", "Wages")
        out = ready.ok("statement", "10000001")
        assert "2026-10-01 to 2026-10-31" in out
        assert "Wages" in out
        assert "£300.00" in out

    def test_statement_for_another_month(self, ready):
        out = ready.ok("statement", "10000001", "--month", "2026-09")
        assert "2026-09-01 to 2026-09-30" in out
        assert "No transactions in this period." in out

    @pytest.mark.parametrize("text", ["2026-13", "October", "2026/10", ""])
    def test_bad_month_is_refused(self, ready, text):
        assert "Month should look like" in ready.fails("statement", "10000001", "--month", text)

    def test_statement_for_a_missing_account(self, ready):
        assert "No account" in ready.fails("statement", "12345678")

    def test_report(self, ready):
        ready.ok("withdraw", "10000001", "300")
        out = ready.ok("report")
        for title in ("Customers", "Account types", "Overdrawn accounts", "This month"):
            assert f"=== {title} ===" in out
        assert "Total held: £950.00" in out
        assert "-£50.00" in out  # the overdrawn current account


class TestAccountStatus:
    def test_freeze_blocks_money_and_unfreeze_lets_it_move(self, ready):
        assert "frozen" in ready.ok("freeze", "10000001")
        assert "frozen" in ready.fails("deposit", "10000001", "5")
        assert "unfrozen" in ready.ok("unfreeze", "10000001")
        ready.ok("deposit", "10000001", "5")

    def test_close_needs_a_zero_balance(self, ready):
        assert "must be £0.00" in ready.fails("close", "10000001")
        ready.ok("withdraw", "10000001", "250")
        assert "closed" in ready.ok("close", "10000001")
        assert not ready.bank.get_account("10000001").is_open

    def test_unfreeze_an_open_account_is_refused(self, ready):
        assert "Only a frozen account" in ready.fails("unfreeze", "10000001")


class TestSaving:
    @pytest.mark.parametrize("argv", [
        ("customers",), ("accounts",), ("statement", "10000001"), ("report",),
    ])
    def test_read_only_commands_never_save(self, ready, argv):
        ready.ok(*argv)
        assert ready.repository.saves == 0

    def test_commands_that_change_the_bank_save_once(self, ready):
        ready.ok("deposit", "10000001", "5")
        assert ready.repository.saves == 1

    def test_file_option_is_passed_on(self, terminal, tmp_path):
        target = tmp_path / "other.json"
        terminal.ok("--file", str(target), "customers")
        assert terminal.paths == [target]

    def test_default_file(self, terminal):
        terminal.ok("customers")
        assert terminal.paths[0].as_posix() == "data/bank.json"

    def test_real_json_file(self, clock, tmp_path):
        path = tmp_path / "bank.json"
        out = io.StringIO()
        cli = BankCLI(clock=clock, out=out, err=io.StringIO())
        assert cli.run(["--file", str(path), "add-customer", "Ronaldo Mudiwa", "r@example.com"]) == 0
        assert cli.run(["--file", str(path), "open", "C0001", "current", "--deposit", "20"]) == 0
        assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
        assert JSONBankRepository(path).load().get_account("10000001").balance == D("20.00")

    def test_damaged_file_gives_a_clear_error(self, clock, tmp_path):
        path = tmp_path / "bank.json"
        path.write_text("{ not json", encoding="utf-8")
        err = io.StringIO()
        cli = BankCLI(clock=clock, out=io.StringIO(), err=err)
        assert cli.run(["--file", str(path), "customers"]) == 1
        assert "not valid JSON" in err.getvalue()
        assert path.read_text(encoding="utf-8") == "{ not json"  # left alone


class TestDemo:
    def test_demo_runs_and_leaves_the_saved_bank_alone(self, terminal):
        terminal.ok("add-customer", "Ronaldo Mudiwa", "ronaldo@example.com")
        terminal.repository.saves = 0
        out = terminal.ok("demo")
        assert "Saving and loading" in out
        assert "Things the bank refuses to do" in out
        assert terminal.repository.saves == 0
        assert len(terminal.bank.customers) == 1

    def test_demo_works_even_if_the_saved_file_is_damaged(self, clock, tmp_path):
        path = tmp_path / "bank.json"
        path.write_text("{ not json", encoding="utf-8")
        cli = BankCLI(clock=clock, out=io.StringIO(), err=io.StringIO())
        assert cli.run(["--file", str(path), "demo"]) == 0


class TestTypingMistakes:
    def test_no_command_shows_usage(self, terminal, capsys):
        with pytest.raises(SystemExit) as stopped:
            terminal.run()
        assert stopped.value.code == 2
        assert "usage" in capsys.readouterr().err

    def test_missing_amount_shows_usage(self, ready, capsys):
        with pytest.raises(SystemExit) as stopped:
            ready.run("deposit", "10000001")
        assert stopped.value.code == 2
        assert ready.repository.saves == 0

    def test_unknown_command(self, terminal, capsys):
        with pytest.raises(SystemExit):
            terminal.run("rob-the-bank")


class TestAddingCommands:
    def test_a_new_command_works_without_editing_the_cli(self, ready):
        class CountCommand(Command):
            name = "count"
            help = "how many accounts there are"

            def run(self, session: Session, args: argparse.Namespace) -> None:
                session.say(f"{len(session.bank)} accounts")

        out = io.StringIO()
        cli = BankCLI(ready.open_repository, [*default_commands(), CountCommand()],
                      clock=ready.clock, out=out)
        assert cli.run(["count"]) == 0
        assert out.getvalue().strip() == "2 accounts"
        assert "count" in cli.command_names

    def test_two_commands_with_the_same_name_are_refused(self):
        with pytest.raises(ValueError, match="deposit"):
            BankCLI(commands=[*default_commands(), default_commands()[4]])

    def test_every_command_has_a_name_and_help(self):
        for command in default_commands():
            assert command.name and command.help

    def test_session_without_a_bank(self, clock):
        session = Session(io.StringIO(), clock())
        with pytest.raises(RuntimeError):
            session.bank


def test_parse_month():
    assert parse_month("2026-02") == (2026, 2)
    assert parse_month(" 2026-10 ") == (2026, 10)
