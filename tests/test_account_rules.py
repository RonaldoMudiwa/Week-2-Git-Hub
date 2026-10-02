"""Rules every kind of account must follow.

Each test runs once for every account type. If a new type breaks any of
these, it can't safely be used in place of an Account, which is what the
Liskov Substitution Principle (the L in SOLID) is about.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from banking import (
    Account,
    AccountNotActiveError,
    AccountStatus,
    CurrentAccount,
    InsufficientFundsError,
    SavingsAccount,
    TransactionType,
    ValidationError,
    WithdrawalError,
)

ACCOUNT_TYPES = [CurrentAccount, SavingsAccount]


@pytest.fixture(params=ACCOUNT_TYPES, ids=lambda cls: cls.__name__)
def make_account(request, clock):
    """Builds an account of each type in turn."""
    def build(opening_balance="100", **options):
        return request.param("12345678", "Ronaldo Mudiwa", opening_balance,
                             clock=clock, **options)
    return build


@pytest.fixture
def account(make_account) -> Account:
    return make_account()


class TestOpening:

    def test_opening_balance(self, account):
        assert account.balance == Decimal("100.00")

    def test_opening_deposit_is_in_the_history(self, account):
        assert account.transactions[0].description == "Opening deposit"

    def test_zero_opening_balance_has_no_history(self, make_account):
        assert make_account("0").transactions == ()

    def test_starts_open(self, account):
        assert account.status is AccountStatus.OPEN and account.is_open

    def test_negative_opening_balance(self, make_account):
        with pytest.raises(ValidationError):
            make_account("-1")

    @pytest.mark.parametrize("number, name", [("", "Ronaldo"), ("123", "  "), (123, "Ronaldo")])
    def test_bad_details(self, number, name):
        for cls in ACCOUNT_TYPES:
            with pytest.raises(ValidationError):
                cls(number, name)

    def test_extra_spaces_in_name_are_squashed(self, clock):
        for cls in ACCOUNT_TYPES:
            assert cls("1", "  Ronaldo   Mudiwa ", clock=clock).owner_name == "Ronaldo Mudiwa"

    def test_base_class_cannot_be_created(self):
        with pytest.raises(TypeError):
            Account("1", "Ronaldo")


class TestDeposit:

    def test_raises_balance(self, account):
        account.deposit("25.50")
        assert account.balance == Decimal("125.50")

    def test_returns_the_history_line(self, account):
        transaction = account.deposit("10", "Birthday money")
        assert transaction is account.transactions[-1]
        assert transaction.kind is TransactionType.DEPOSIT
        assert transaction.balance_after == Decimal("110.00")
        assert transaction.description == "Birthday money"

    @pytest.mark.parametrize("bad", ["0", "-5", "abc", 5.5])
    def test_bad_amount_changes_nothing(self, account, bad):
        with pytest.raises(ValidationError):
            account.deposit(bad)
        assert account.balance == Decimal("100.00")
        assert len(account.transactions) == 1

    def test_blank_description(self, account):
        with pytest.raises(ValidationError):
            account.deposit("5", "   ")


class TestWithdraw:

    def test_lowers_balance(self, account):
        account.withdraw("30")
        assert account.balance == Decimal("70.00")

    def test_can_take_everything(self, account):
        account.withdraw("100")
        assert account.balance == Decimal("0.00")

    def test_too_much_raises_withdrawal_error(self, account):
        # Every account type must use WithdrawalError (or a child of it),
        # so code using any account can catch the same error.
        with pytest.raises(WithdrawalError):
            account.withdraw("1000000")

    def test_failed_withdrawal_changes_nothing(self, account):
        with pytest.raises(InsufficientFundsError):
            account.withdraw("1000000")
        assert account.balance == Decimal("100.00")
        assert len(account.transactions) == 1

    def test_never_goes_below_what_is_available(self, account):
        account.withdraw(account.available_to_withdraw)
        assert account.available_to_withdraw == Decimal("0.00")


class TestHistory:

    def test_is_a_read_only_copy(self, account):
        history = account.transactions
        assert isinstance(history, tuple)
        assert not hasattr(history, "append")

    def test_balances_add_up(self, account):
        account.deposit("40")
        account.withdraw("15")
        total = sum(t.signed_amount for t in account.transactions)
        assert total == account.balance

    def test_uses_the_clock(self, account, clock):
        clock.advance(days=3)
        assert account.deposit("1").timestamp == clock.now

    def test_balance_cannot_be_set_directly(self, account):
        with pytest.raises(AttributeError):
            account.balance = Decimal("1000000")


class TestStatus:

    def test_frozen_blocks_deposits_and_withdrawals(self, account):
        account.freeze()
        with pytest.raises(AccountNotActiveError):
            account.deposit("1")
        with pytest.raises(AccountNotActiveError):
            account.withdraw("1")

    def test_unfreeze(self, account):
        account.freeze()
        account.unfreeze()
        account.deposit("1")
        assert account.is_open

    def test_unfreeze_when_not_frozen(self, account):
        with pytest.raises(AccountNotActiveError):
            account.unfreeze()

    def test_close_needs_zero_balance(self, account):
        with pytest.raises(ValidationError, match="£100.00"):
            account.close()
        account.withdraw("100")
        account.close()
        assert account.status is AccountStatus.CLOSED

    def test_closed_is_final(self, make_account):
        account = make_account("0")
        account.close()
        with pytest.raises(AccountNotActiveError):
            account.deposit("1")
        with pytest.raises(AccountNotActiveError):
            account.freeze()
        with pytest.raises(AccountNotActiveError):
            account.close()


class TestEquality:

    def test_same_number_means_same_account(self, clock):
        assert CurrentAccount("1", "A", clock=clock) == CurrentAccount("1", "B", clock=clock)

    def test_different_numbers(self, clock):
        assert CurrentAccount("1", "A", clock=clock) != CurrentAccount("2", "A", clock=clock)

    def test_works_in_a_set(self, clock):
        accounts = {CurrentAccount("1", "A", clock=clock), CurrentAccount("1", "A", clock=clock)}
        assert len(accounts) == 1

    def test_str_and_repr(self, account):
        assert "12345678" in str(account) and "£100.00" in str(account)
        assert "Decimal('100.00')" in repr(account)
