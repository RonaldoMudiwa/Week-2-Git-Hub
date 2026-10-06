"""The command line interface.

Each command loads the saved bank, does one job, and saves again if
anything changed. Run it from the project root:

    python -m banking add-customer "Ronaldo Mudiwa" ronaldo@example.com
    python -m banking open C0001 current --deposit 250 --overdraft 200
    python -m banking statement 10000001

Add --help after any command to see its options.
"""

from __future__ import annotations

import argparse
import sys
from abc import ABC, abstractmethod
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO

from .account import Account, Clock
from .bank import Bank
from .exceptions import BankError, ValidationError
from .money import format_money
from .policies import FlatMonthlyFee
from .reports import BankReport, TextFormatter
from .statements import Statement
from .storage import BankRepository, JSONBankRepository

DEFAULT_FILE = Path("data") / "bank.json"
DEFAULT_BANK_NAME = "Mudiwa Bank"

# Given the --file path, returns where to save and load the bank.
RepositoryFactory = Callable[[Path], BankRepository]


class Session:
    """What a command gets to work with while it runs."""

    def __init__(self, out: TextIO, today: datetime, bank: Bank | None = None) -> None:
        self.out = out
        self.today = today
        self.formatter = TextFormatter()
        self._bank = bank

    @property
    def bank(self) -> Bank:
        if self._bank is None:
            raise RuntimeError("This command was run without a bank.")
        return self._bank

    def say(self, text: str = "") -> None:
        print(text, file=self.out)


class Command(ABC):
    """One thing the user can ask for, such as "deposit" or "report".

    Every command is its own small class. Adding a new one means writing a
    new class, never editing the others.
    """

    name = ""
    help = ""
    changes_bank = False  # if True, the bank is saved after the command works
    needs_bank = True     # if False, the saved bank isn't loaded at all

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add this command's own options. Commands with none can skip it."""

    @abstractmethod
    def run(self, session: Session, args: argparse.Namespace) -> None:
        """Do the job. Raise a BankError if it can't be done."""


# ----------------------------------------------------------------------
# Customers
# ----------------------------------------------------------------------

class AddCustomerCommand(Command):
    name = "add-customer"
    help = "add a new customer"
    changes_bank = True

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name", help='full name, in quotes if it has spaces')
        parser.add_argument("email")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        customer = session.bank.add_customer(args.name, args.email)
        session.say(f"Added {customer}.")


class CustomersCommand(Command):
    name = "customers"
    help = "list every customer"

    def run(self, session: Session, args: argparse.Namespace) -> None:
        session.say(session.formatter.customer_list(session.bank.customers))


# ----------------------------------------------------------------------
# Accounts
# ----------------------------------------------------------------------

class OpenAccountCommand(Command):
    name = "open"
    help = "open an account for a customer"
    changes_bank = True

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("customer_id", help="e.g. C0001")
        parser.add_argument("account_type", help="current or savings")
        parser.add_argument("--deposit", default="0", help="money to pay in when it opens")
        parser.add_argument("--overdraft", help="overdraft limit (current accounts)")
        parser.add_argument("--rate", help="yearly interest rate in %% (savings accounts)")
        parser.add_argument("--max-withdrawals", type=int,
                            help="withdrawals allowed each month (savings accounts)")
        parser.add_argument("--monthly-fee", help="a flat charge taken at each month end")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        account = session.bank.open_account(args.customer_id, args.account_type,
                                            args.deposit, **self._options(args))
        session.say(f"Opened {account}.")

    @staticmethod
    def _options(args: argparse.Namespace) -> dict[str, Any]:
        """Only pass on what the user typed. The account type decides if it's allowed."""
        options: dict[str, Any] = {}
        if args.overdraft is not None:
            options["overdraft_limit"] = args.overdraft
        if args.rate is not None:
            options["interest_rate"] = args.rate
        if args.max_withdrawals is not None:
            options["max_withdrawals_per_month"] = args.max_withdrawals
        if args.monthly_fee is not None:
            options["fee_policy"] = FlatMonthlyFee(args.monthly_fee)
        return options


class AccountsCommand(Command):
    name = "accounts"
    help = "list accounts, for everyone or one customer"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("customer_id", nargs="?", help="leave out to list every account")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        bank = session.bank
        accounts = list(bank) if args.customer_id is None else bank.accounts_for(args.customer_id)
        session.say(session.formatter.account_list(accounts))


class _AccountActionCommand(Command):
    """Shared by freeze, unfreeze and close: pick one account and do one thing to it."""

    changes_bank = True
    done = ""  # e.g. "frozen", for the message at the end

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("account", help="account number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        account = session.bank.get_account(args.account)
        self.act(session.bank, account)
        session.say(f"Account {account.account_number} {self.done}.")

    @abstractmethod
    def act(self, bank: Bank, account: Account) -> None:
        """Make the change."""


class FreezeCommand(_AccountActionCommand):
    name = "freeze"
    help = "block all money moving in or out of an account"
    done = "frozen"

    def act(self, bank: Bank, account: Account) -> None:
        account.freeze()


class UnfreezeCommand(_AccountActionCommand):
    name = "unfreeze"
    help = "let money move again on a frozen account"
    done = "unfrozen"

    def act(self, bank: Bank, account: Account) -> None:
        account.unfreeze()


class CloseCommand(_AccountActionCommand):
    name = "close"
    help = "close an account for good (balance must be zero)"
    done = "closed"

    def act(self, bank: Bank, account: Account) -> None:
        bank.close_account(account.account_number)


# ----------------------------------------------------------------------
# Moving money
# ----------------------------------------------------------------------

class DepositCommand(Command):
    name = "deposit"
    help = "pay money into an account"
    changes_bank = True

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("account", help="account number")
        parser.add_argument("amount", help="e.g. 50 or 12.99")
        parser.add_argument("--note", default="Deposit", help="what it's for")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        account = session.bank.get_account(args.account)
        line = account.deposit(args.amount, args.note)
        session.say(f"Paid {format_money(line.amount)} into {account.account_number}. "
                    f"Balance is now {format_money(account.balance)}.")


class WithdrawCommand(Command):
    name = "withdraw"
    help = "take money out of an account"
    changes_bank = True

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("account", help="account number")
        parser.add_argument("amount", help="e.g. 50 or 12.99")
        parser.add_argument("--note", default="Withdrawal", help="what it's for")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        account = session.bank.get_account(args.account)
        line = account.withdraw(args.amount, args.note)
        session.say(f"Took {format_money(line.amount)} out of {account.account_number}. "
                    f"Balance is now {format_money(account.balance)}.")


class TransferCommand(Command):
    name = "transfer"
    help = "move money from one account to another"
    changes_bank = True

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("from_account", help="account the money leaves")
        parser.add_argument("to_account", help="account the money goes into")
        parser.add_argument("amount", help="e.g. 50 or 12.99")
        parser.add_argument("--note", help="what it's for")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        money_out, _ = session.bank.transfer(args.from_account, args.to_account,
                                             args.amount, args.note)
        session.say(f"Moved {format_money(money_out.amount)} from {args.from_account} "
                    f"to {args.to_account}.")


class MonthEndCommand(Command):
    name = "month-end"
    help = "pay this month's interest and take this month's fees"
    changes_bank = True

    def run(self, session: Session, args: argparse.Namespace) -> None:
        changes = session.bank.run_month_end()
        if not changes:
            session.say("Nothing to pay or charge this month.")
            return
        for number, lines in changes.items():
            for line in lines:
                session.say(f"{number}  {line.description:<18}{format_money(line.signed_amount):>12}")
        session.say(f"Month end done. {len(changes)} account(s) changed.")


# ----------------------------------------------------------------------
# Statements and reports
# ----------------------------------------------------------------------

class StatementCommand(Command):
    name = "statement"
    help = "show one account's statement for a month"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("account", help="account number")
        parser.add_argument("--month", help="YYYY-MM, e.g. 2026-10 (default: this month)")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        account = session.bank.get_account(args.account)
        if args.month is None:
            year, month = session.today.year, session.today.month
        else:
            year, month = parse_month(args.month)
        statement = Statement.for_month(account, year, month)
        session.say(session.formatter.statement(statement))


class ReportCommand(Command):
    name = "report"
    help = "the bank manager's view: customers, totals and overdrafts"

    def run(self, session: Session, args: argparse.Namespace) -> None:
        bank = session.bank
        report = BankReport(bank)
        formatter = session.formatter
        today = session.today
        sections = [
            ("Customers", formatter.customer_table(report.customer_summaries())),
            ("Account types", formatter.type_table(report.totals_by_account_type())),
            ("Overdrawn accounts", formatter.overdrawn_table(report.overdrawn_accounts())),
            ("This month", formatter.month_activity(report.month_activity(today.year, today.month))),
        ]
        session.say(bank.name)
        for title, table in sections:
            session.say(f"\n=== {title} ===")
            session.say(table)
        session.say(f"\nTotal held: {format_money(bank.total_deposits)}")


class DemoCommand(Command):
    name = "demo"
    help = "run a short tour with made up customers (your saved bank isn't touched)"
    needs_bank = False

    def run(self, session: Session, args: argparse.Namespace) -> None:
        from . import demo  # only loaded when someone asks for the demo

        with redirect_stdout(session.out):
            demo.main()


def parse_month(text: str) -> tuple[int, int]:
    """Turn "2026-10" into (2026, 10)."""
    try:
        parsed = datetime.strptime(text.strip(), "%Y-%m")
    except ValueError:
        raise ValidationError(f"Month should look like 2026-10, got {text!r}.") from None
    return parsed.year, parsed.month


def default_commands() -> list[Command]:
    return [
        AddCustomerCommand(), CustomersCommand(),
        OpenAccountCommand(), AccountsCommand(),
        DepositCommand(), WithdrawCommand(), TransferCommand(),
        StatementCommand(), MonthEndCommand(), ReportCommand(),
        FreezeCommand(), UnfreezeCommand(), CloseCommand(),
        DemoCommand(),
    ]


class BankCLI:
    """Reads what was typed, runs the matching command, and saves the bank.

    Where the bank is stored, the clock and the output are all passed in, so
    tests can run every command without touching real files.
    """

    def __init__(
        self,
        open_repository: RepositoryFactory | None = None,
        commands: Sequence[Command] | None = None,
        clock: Clock | None = None,
        out: TextIO | None = None,
        err: TextIO | None = None,
    ) -> None:
        self._clock = clock or datetime.now
        self._open_repository = open_repository or self._json_file
        self._out = out or sys.stdout
        self._err = err or sys.stderr

        self._commands: dict[str, Command] = {}
        for command in (commands if commands is not None else default_commands()):
            if command.name in self._commands:
                raise ValueError(f"Two commands are called {command.name!r}.")
            self._commands[command.name] = command

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(self._commands)

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="python -m banking",
            description="A small bank you run from the terminal.",
        )
        parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                            help=f"where the bank is saved (default: {DEFAULT_FILE})")
        subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")
        for command in self._commands.values():
            sub = subparsers.add_parser(command.name, help=command.help, description=command.help)
            command.add_arguments(sub)
        return parser

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Run one command. Returns 0 if it worked, 1 if the bank said no.

        Typing mistakes, like a missing amount, are caught by argparse, which
        prints the usage and exits with 2.
        """
        args = self.build_parser().parse_args(argv)
        command = self._commands[args.command]
        try:
            repository = self._open_repository(args.file)
            bank = self._load_or_create(repository) if command.needs_bank else None
            command.run(Session(self._out, self._clock(), bank), args)
            # Only saved once the command has fully worked, so a refused
            # withdrawal or a typo never changes the saved file.
            if command.changes_bank:
                repository.save(bank)
        except BankError as error:
            print(f"Error: {error}", file=self._err)
            return 1
        return 0

    def _load_or_create(self, repository: BankRepository) -> Bank:
        bank = repository.load()
        return bank if bank is not None else Bank(DEFAULT_BANK_NAME, clock=self._clock)

    def _json_file(self, path: Path) -> BankRepository:
        return JSONBankRepository(path, clock=self._clock)


def main(argv: Sequence[str] | None = None) -> int:
    return BankCLI().run(argv)
