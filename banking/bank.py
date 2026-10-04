"""The Bank: looks after customers and their accounts, and moves money between them."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator

from .account import Account, Clock
from .account_numbers import AccountNumberGenerator, SequentialAccountNumberGenerator
from .current_account import CurrentAccount
from .customer import Customer
from .exceptions import (
    AccountNotActiveError,
    AccountNotFoundError,
    CustomerNotFoundError,
    DuplicateCustomerError,
    ValidationError,
)
from .money import ZERO, positive_amount
from .savings_account import SavingsAccount
from .transaction import Transaction

# The account types every new Bank starts with.
DEFAULT_ACCOUNT_TYPES: tuple[type[Account], ...] = (CurrentAccount, SavingsAccount)


class Bank:
    """Keeps track of customers and accounts.

    The Bank doesn't know how any account works inside. It only uses what
    every Account offers, so new account types can be added with
    register_account_type() without changing this class.

        >>> bank = Bank("Mudiwa Bank")
        >>> ronaldo = bank.add_customer("Ronaldo Mudiwa", "ronaldo@example.com")
        >>> current = bank.open_account(ronaldo.customer_id, "current", "100")
    """

    def __init__(
        self,
        name: str,
        number_generator: AccountNumberGenerator | None = None,
        clock: Clock | None = None,
    ) -> None:
        """
        Args:
            name: The bank's name.
            number_generator: Hands out account numbers. Defaults to
                10000001, 10000002 and so on.
            clock: Returns the current time. Passed on to every account.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("Bank name can't be blank.")
        self._name = name.strip()
        self._numbers = number_generator or SequentialAccountNumberGenerator()
        self._clock = clock or datetime.now

        self._customers: dict[str, Customer] = {}
        self._accounts: dict[str, Account] = {}
        self._owners: dict[str, str] = {}  # account number -> customer id
        self._account_types: dict[str, type[Account]] = {}
        for account_class in DEFAULT_ACCOUNT_TYPES:
            self.register_account_type(account_class)

    @property
    def name(self) -> str:
        return self._name

    # ------------------------------------------------------------------
    # Account types
    # ------------------------------------------------------------------

    def register_account_type(self, account_class: type[Account]) -> None:
        """Allow a new kind of account to be opened, using its ACCOUNT_TYPE as the name."""
        if not (isinstance(account_class, type) and issubclass(account_class, Account)):
            raise ValidationError("Only Account subclasses can be registered.")
        self._account_types[account_class.ACCOUNT_TYPE] = account_class

    @property
    def account_types(self) -> tuple[str, ...]:
        return tuple(self._account_types)

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    def add_customer(self, name: str, email: str) -> Customer:
        """Create a customer with the next id, e.g. "C0001".

        Raises:
            DuplicateCustomerError: If that email is already used.
            ValidationError: If the name or email isn't allowed.
        """
        customer_id = f"C{len(self._customers) + 1:04d}"
        customer = Customer(customer_id, name, email)
        if any(c.email == customer.email for c in self._customers.values()):
            raise DuplicateCustomerError(f"A customer with email {customer.email} already exists.")
        self._customers[customer_id] = customer
        return customer

    def get_customer(self, customer_id: str) -> Customer:
        try:
            return self._customers[customer_id]
        except KeyError:
            raise CustomerNotFoundError(f"No customer with id {customer_id!r}.") from None

    @property
    def customers(self) -> tuple[Customer, ...]:
        return tuple(self._customers.values())

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def open_account(
        self,
        customer_id: str,
        account_type: str = "current",
        opening_balance: Decimal | int | str = "0",
        **options,
    ) -> Account:
        """Open a new account for a customer.

        Args:
            customer_id: Who it belongs to.
            account_type: "current", "savings", or any registered type.
            opening_balance: Money paid in to start with.
            **options: Passed on to that account type, e.g.
                overdraft_limit="200" or interest_rate="4.5".

        Raises:
            CustomerNotFoundError: If the customer doesn't exist.
            ValidationError: If the type or an option isn't allowed.
        """
        customer = self.get_customer(customer_id)
        account_class = self._account_types.get(account_type)
        if account_class is None:
            allowed = ", ".join(self._account_types)
            raise ValidationError(f"Unknown account type {account_type!r}. Choose from: {allowed}.")

        try:
            account = account_class(self._numbers.next_number(), customer.name,
                                    opening_balance, clock=self._clock, **options)
        except TypeError as error:
            # Python raises TypeError for an option the class doesn't take.
            raise ValidationError(f"Bad option for a {account_type} account: {error}") from error

        self._accounts[account.account_number] = account
        self._owners[account.account_number] = customer.customer_id
        return account

    def get_account(self, account_number: str) -> Account:
        try:
            return self._accounts[account_number]
        except KeyError:
            raise AccountNotFoundError(f"No account with number {account_number!r}.") from None

    def accounts_for(self, customer_id: str) -> list[Account]:
        """Every account a customer owns, in the order they were opened."""
        self.get_customer(customer_id)  # raises if they don't exist
        return [self._accounts[number] for number, owner in self._owners.items()
                if owner == customer_id]

    def owner_of(self, account_number: str) -> Customer:
        self.get_account(account_number)
        return self._customers[self._owners[account_number]]

    def close_account(self, account_number: str) -> Account:
        """Close an account. Its balance must be zero. It stays on record."""
        account = self.get_account(account_number)
        account.close()
        return account

    # ------------------------------------------------------------------
    # Moving money
    # ------------------------------------------------------------------

    def transfer(
        self,
        from_number: str,
        to_number: str,
        amount: Decimal | int | str,
        description: str | None = None,
    ) -> tuple[Transaction, Transaction]:
        """Move money from one account to another.

        Either both sides happen or neither does. Money can't leave one
        account without arriving in the other.

        Returns:
            The history line from each account: (money out, money in).

        Raises:
            AccountNotFoundError: If either account doesn't exist.
            ValidationError: If it's the same account, or a bad amount.
            AccountNotActiveError: If either account is frozen or closed.
            WithdrawalError: If the sending account's rules don't allow it.
        """
        source = self.get_account(from_number)
        target = self.get_account(to_number)
        if source == target:
            raise ValidationError("Can't transfer money to the same account.")
        value = positive_amount(amount)

        # Check the receiving side first, so we never take money we can't deliver.
        if not target.is_open:
            raise AccountNotActiveError(f"Account {to_number} is {target.status.value}.")

        money_out = source.send_transfer(value, to_number, description)
        try:
            money_in = target.receive_transfer(value, from_number, description)
        except Exception:
            # Shouldn't happen after the checks above, but if it does, give
            # the money back so it isn't lost. The refund shows in the history.
            source.receive_transfer(value, to_number, "Transfer reversed")
            raise
        return money_out, money_in

    # ------------------------------------------------------------------
    # Month end
    # ------------------------------------------------------------------

    def run_month_end(self) -> dict[str, list[Transaction]]:
        """Pay interest and take fees on every account.

        The Bank doesn't know how any account works these out. It just asks
        each one to apply its own rules. Accounts that are closed or have
        already been done this month are skipped, so running it twice by
        mistake does no harm.

        Returns:
            Each account number that changed, with the lines added to it.
        """
        changes: dict[str, list[Transaction]] = {}
        for account in self._accounts.values():
            if account.month_end_done:
                continue
            added = account.apply_month_end()
            if added:
                changes[account.account_number] = added
        return changes

    # ------------------------------------------------------------------
    # Saving and loading
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """The whole bank as a plain dictionary for JSON.

        Each account and customer saves itself, so this method doesn't need
        to know what's inside any of them.
        """
        return {
            "name": self._name,
            "customers": [c.to_dict() for c in self._customers.values()],
            "accounts": [
                {"owner": self._owners[number], **account.to_dict()}
                for number, account in self._accounts.items()
            ],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        clock: Clock | None = None,
        extra_account_types: tuple[type[Account], ...] = (),
    ) -> "Bank":
        """Rebuild a bank from what to_dict made.

        New account numbers carry on from the highest one saved, so a loaded
        bank never hands out a number that's already taken.

        Args:
            data: What to_dict made.
            clock: Returns the current time. Passed on to every account.
            extra_account_types: Any account types registered beyond the
                standard ones, so their accounts can be rebuilt.

        Raises:
            ValidationError: If anything is missing or doesn't make sense.
        """
        try:
            name = data["name"]
            customers = [Customer.from_dict(item) for item in data.get("customers", [])]
            account_items = list(data.get("accounts", []))
        except (KeyError, TypeError) as error:
            raise ValidationError(f"Saved bank is missing or has a bad {error}.") from error

        numbers = [int(item["account_number"]) for item in account_items
                   if str(item.get("account_number", "")).isdigit()]
        start = max(numbers) + 1 if numbers else 10000001
        bank = cls(name, SequentialAccountNumberGenerator(start), clock)
        for account_class in extra_account_types:
            bank.register_account_type(account_class)

        for customer in customers:
            if customer.customer_id in bank._customers:
                raise ValidationError(f"Customer {customer.customer_id} is saved twice.")
            bank._customers[customer.customer_id] = customer

        for item in account_items:
            account_class = bank._account_types.get(item.get("type"))
            if account_class is None:
                raise ValidationError(f"Unknown account type {item.get('type')!r}.")
            owner = item.get("owner")
            if owner not in bank._customers:
                raise ValidationError(f"Account {item.get('account_number')} has an unknown owner.")
            account = account_class.from_dict(item, clock=bank._clock)
            if account.account_number in bank._accounts:
                raise ValidationError(f"Account {account.account_number} is saved twice.")
            bank._accounts[account.account_number] = account
            bank._owners[account.account_number] = owner
        return bank

    # ------------------------------------------------------------------
    # Totals and container behaviour
    # ------------------------------------------------------------------

    @property
    def total_deposits(self) -> Decimal:
        """All balances added together. Overdrafts count as negative."""
        return sum((a.balance for a in self._accounts.values()), start=ZERO)

    def __len__(self) -> int:
        """Number of accounts."""
        return len(self._accounts)

    def __iter__(self) -> Iterator[Account]:
        return iter(self._accounts.values())

    def __contains__(self, account_number: object) -> bool:
        return account_number in self._accounts

    def __repr__(self) -> str:
        return (f"Bank({self._name!r}, customers={len(self._customers)}, "
                f"accounts={len(self._accounts)})")
