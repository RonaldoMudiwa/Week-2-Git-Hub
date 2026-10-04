"""The base class every kind of bank account inherits from."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from .enums import AccountStatus, TransactionType
from .exceptions import (
    AccountNotActiveError,
    InsufficientFundsError,
    ValidationError,
)
from .money import ZERO, format_money, positive_amount, to_money
from .policies import FeePolicy, InterestPolicy, NoFee, NoInterest, policy_from_dict
from .transaction import Transaction

# A function that returns the current time. Passed in so tests can pretend
# it is any date they like.
Clock = Callable[[], datetime]


class Account(ABC):
    """A bank account that holds money and keeps a history.

    The balance can only change through deposit() and withdraw(), and every
    change is written to the history. Nothing outside the class can edit the
    balance directly, so the history always adds up.

    Subclasses decide how much can be taken out by providing
    available_to_withdraw, and can add their own rules by extending
    _check_withdrawal.
    """

    ACCOUNT_TYPE = "account"

    def __init__(
        self,
        account_number: str,
        owner_name: str,
        opening_balance: Decimal | int | str = "0",
        clock: Clock | None = None,
        *,
        interest_policy: InterestPolicy | None = None,
        fee_policy: FeePolicy | None = None,
    ) -> None:
        """
        Args:
            account_number: Unique number for this account.
            owner_name: Name of the account holder.
            opening_balance: Money paid in when the account opens.
            clock: Returns the current time. Defaults to the real time.
            interest_policy: How monthly interest is worked out. Default: none.
            fee_policy: What is charged each month. Default: nothing.

        Raises:
            ValidationError: If any value is not allowed.
        """
        self._account_number = self._clean_text(account_number, "Account number")
        self._owner_name = self._clean_text(owner_name, "Owner name")
        self._clock = clock or datetime.now
        self._status = AccountStatus.OPEN
        self._balance = ZERO
        self._transactions: list[Transaction] = []
        self.interest_policy = interest_policy or NoInterest()
        self.fee_policy = fee_policy or NoFee()
        self._last_month_end: tuple[int, int] | None = None  # (year, month)

        opening = to_money(opening_balance)
        if opening < ZERO:
            raise ValidationError("Opening balance can't be negative.")
        if opening > ZERO:
            self.deposit(opening, "Opening deposit")

    # ------------------------------------------------------------------
    # Read-only details
    # ------------------------------------------------------------------

    @property
    def account_number(self) -> str:
        return self._account_number

    @property
    def owner_name(self) -> str:
        return self._owner_name

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def status(self) -> AccountStatus:
        return self._status

    @property
    def is_open(self) -> bool:
        return self._status is AccountStatus.OPEN

    @property
    def transactions(self) -> tuple[Transaction, ...]:
        """The full history, oldest first.

        A tuple, so the caller gets a copy they can't add to or delete from.
        """
        return tuple(self._transactions)

    @property
    def interest_policy(self) -> InterestPolicy:
        return self._interest_policy

    @interest_policy.setter
    def interest_policy(self, policy: InterestPolicy) -> None:
        if not isinstance(policy, InterestPolicy):
            raise ValidationError("interest_policy must be an InterestPolicy.")
        self._interest_policy = policy

    @property
    def fee_policy(self) -> FeePolicy:
        return self._fee_policy

    @fee_policy.setter
    def fee_policy(self, policy: FeePolicy) -> None:
        if not isinstance(policy, FeePolicy):
            raise ValidationError("fee_policy must be a FeePolicy.")
        self._fee_policy = policy

    # ------------------------------------------------------------------
    # What subclasses must provide
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def available_to_withdraw(self) -> Decimal:
        """The most that could be taken out right now."""

    # ------------------------------------------------------------------
    # Moving money
    # ------------------------------------------------------------------

    def deposit(self, amount: Decimal | int | str, description: str = "Deposit") -> Transaction:
        """Pay money in and return the new history line.

        Raises:
            ValidationError: If the amount isn't above zero.
            AccountNotActiveError: If the account is frozen or closed.
        """
        return self._credit(TransactionType.DEPOSIT, amount, description)

    def withdraw(self, amount: Decimal | int | str, description: str = "Withdrawal") -> Transaction:
        """Take money out and return the new history line.

        Raises:
            ValidationError: If the amount isn't above zero.
            AccountNotActiveError: If the account is frozen or closed.
            WithdrawalError: If this account's rules don't allow it.
                Each account type raises a child of this error, so
                catching WithdrawalError works for all of them.
        """
        return self._debit(TransactionType.WITHDRAWAL, amount, description)

    def send_transfer(self, amount: Decimal | int | str, to_account: str,
                      description: str | None = None) -> Transaction:
        """Take money out as a transfer to another account.

        Follows the same rules as withdraw(), so a savings account's monthly
        limit counts transfers too. The Bank calls this, not users directly.
        """
        return self._debit(TransactionType.TRANSFER_OUT, amount,
                           description or f"Transfer to {to_account}")

    def receive_transfer(self, amount: Decimal | int | str, from_account: str,
                         description: str | None = None) -> Transaction:
        """Pay money in as a transfer from another account."""
        return self._credit(TransactionType.TRANSFER_IN, amount,
                            description or f"Transfer from {from_account}")

    def _credit(self, kind: TransactionType, amount: Decimal | int | str,
                description: str) -> Transaction:
        """Add money. Every kind of money in goes through here."""
        self._require_open()
        value = positive_amount(amount)
        return self._record(kind, value, self._balance + value, description)

    def _debit(self, kind: TransactionType, amount: Decimal | int | str,
               description: str) -> Transaction:
        """Remove money. Every kind of money out goes through here."""
        self._require_open()
        value = positive_amount(amount)
        self._check_withdrawal(value, kind)
        return self._record(kind, value, self._balance - value, description)

    def _check_withdrawal(self, amount: Decimal, kind: TransactionType) -> None:
        """Raise if this withdrawal isn't allowed.

        Subclasses add their own rules and then call super(), so the money
        check below always runs.
        """
        if amount > self.available_to_withdraw:
            raise InsufficientFundsError(
                f"Can't take out {format_money(amount)}. "
                f"Only {format_money(self.available_to_withdraw)} is available."
            )

    def _record(self, kind: TransactionType, amount: Decimal, new_balance: Decimal,
                description: str) -> Transaction:
        """Change the balance and write the history line together, so they can't disagree."""
        transaction = Transaction(
            kind=kind,
            amount=amount,
            balance_after=new_balance,
            description=self._clean_text(description, "Description"),
            timestamp=self._clock(),
        )
        self._balance = new_balance
        self._transactions.append(transaction)
        return transaction

    # ------------------------------------------------------------------
    # Month end
    # ------------------------------------------------------------------

    @property
    def month_end_done(self) -> bool:
        """True if this month's interest and fees have already been applied."""
        now = self._clock()
        return self._last_month_end == (now.year, now.month)

    def apply_month_end(self) -> list[Transaction]:
        """Pay this month's interest, then take this month's fees.

        The account's own policies decide the amounts, so this method works
        the same for every kind of account. Frozen accounts still get
        interest and fees, like a real bank. Closed accounts are skipped.

        Returns:
            The history lines added. Empty if there was nothing to do.

        Raises:
            ValidationError: If it has already been run this month.
        """
        if self._status is AccountStatus.CLOSED:
            return []
        if self.month_end_done:
            raise ValidationError(
                f"Month end has already been run on {self._account_number} this month."
            )

        added = []
        interest = self._interest_policy.monthly_interest(self._balance)
        if interest > ZERO:
            added.append(self._record(TransactionType.INTEREST, interest,
                                      self._balance + interest, "Monthly interest"))

        # Fees skip the usual withdrawal checks on purpose. A bank charge is
        # taken even if it pushes the account past its overdraft.
        fee = self._fee_policy.monthly_fee(self._balance)
        if fee > ZERO:
            added.append(self._record(TransactionType.FEE, fee,
                                      self._balance - fee, "Monthly fee"))

        now = self._clock()
        self._last_month_end = (now.year, now.month)
        return added

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def freeze(self) -> None:
        """Block all money movement until unfreeze() is called."""
        if self._status is AccountStatus.CLOSED:
            raise AccountNotActiveError("A closed account can't be frozen.")
        self._status = AccountStatus.FROZEN

    def unfreeze(self) -> None:
        if self._status is not AccountStatus.FROZEN:
            raise AccountNotActiveError("Only a frozen account can be unfrozen.")
        self._status = AccountStatus.OPEN

    def close(self) -> None:
        """Close for good. The balance must be exactly zero first.

        Raises:
            AccountNotActiveError: If it is already closed.
            ValidationError: If there is still money in it, or money owed.
        """
        if self._status is AccountStatus.CLOSED:
            raise AccountNotActiveError("This account is already closed.")
        if self._balance != ZERO:
            raise ValidationError(
                f"Balance must be £0.00 to close, it is {format_money(self._balance)}."
            )
        self._status = AccountStatus.CLOSED

    def _require_open(self) -> None:
        if self._status is not AccountStatus.OPEN:
            raise AccountNotActiveError(
                f"Account {self._account_number} is {self._status.value}."
            )

    # ------------------------------------------------------------------
    # Saving and loading
    # ------------------------------------------------------------------

    def settings(self) -> dict[str, Any]:
        """Extra values a subclass needs to be rebuilt, e.g. its overdraft limit."""
        return {}

    def to_dict(self) -> dict[str, Any]:
        """Everything about the account as a plain dictionary for JSON."""
        return {
            "type": self.ACCOUNT_TYPE,
            "account_number": self._account_number,
            "owner_name": self._owner_name,
            "status": self._status.value,
            "last_month_end": list(self._last_month_end) if self._last_month_end else None,
            "settings": self.settings(),
            "interest_policy": self._interest_policy.to_dict(),
            "fee_policy": self._fee_policy.to_dict(),
            "transactions": [t.to_dict() for t in self._transactions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], clock: Clock | None = None) -> "Account":
        """Rebuild an account, history and all, from what to_dict made.

        Works for every subclass, because each one is built through its own
        constructor using its own settings().

        Raises:
            ValidationError: If anything is missing, not valid, or the
                history doesn't add up.
        """
        try:
            account = cls(
                data["account_number"],
                data["owner_name"],
                clock=clock,
                interest_policy=policy_from_dict(data["interest_policy"]),
                fee_policy=policy_from_dict(data["fee_policy"]),
                **data.get("settings", {}),
            )
            history = [Transaction.from_dict(item) for item in data.get("transactions", [])]
            status = AccountStatus(data.get("status", "open"))
            last = data.get("last_month_end")
            last_month_end = (int(last[0]), int(last[1])) if last else None
        except KeyError as error:
            raise ValidationError(f"Account is missing {error}.") from error
        except (TypeError, ValueError) as error:
            raise ValidationError(f"Account has a bad value: {error}") from error

        account._restore(history, status, last_month_end)
        return account

    def _restore(self, history: list[Transaction], status: AccountStatus,
                 last_month_end: tuple[int, int] | None) -> None:
        """Put back saved history, checking every line adds up first.

        The balance isn't saved separately. It is worked out from the
        history, so the two can never disagree.
        """
        running = ZERO
        for line in history:
            running += line.signed_amount
            if line.balance_after != running:
                raise ValidationError(
                    f"History for {self._account_number} doesn't add up at "
                    f"{line.transaction_id}: expected {running}, found {line.balance_after}."
                )
        self._transactions = list(history)
        self._balance = running
        self._status = status
        self._last_month_end = last_month_end

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be text, got {type(value).__name__}.")
        cleaned = " ".join(value.split())  # squash extra spaces
        if not cleaned:
            raise ValidationError(f"{field_name} can't be blank.")
        return cleaned

    def __eq__(self, other: object) -> bool:
        """Two accounts are the same if they have the same number."""
        if not isinstance(other, Account):
            return NotImplemented
        return self._account_number == other._account_number

    def __hash__(self) -> int:
        return hash(self._account_number)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(account_number={self._account_number!r}, "
            f"owner_name={self._owner_name!r}, balance={self._balance!r})"
        )

    def __str__(self) -> str:
        return (
            f"{self.ACCOUNT_TYPE.title()} account {self._account_number} "
            f"({self._owner_name}): {format_money(self._balance)}"
        )
