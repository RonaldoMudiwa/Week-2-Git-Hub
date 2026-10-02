"""Tests for the Bank."""

from __future__ import annotations

from decimal import Decimal

import pytest

from banking import (
    AccountNotActiveError,
    AccountNotFoundError,
    Bank,
    CurrentAccount,
    CustomerNotFoundError,
    DuplicateCustomerError,
    InsufficientFundsError,
    NotFoundError,
    SavingsAccount,
    SequentialAccountNumberGenerator,
    TransactionType,
    ValidationError,
    WithdrawalError,
    WithdrawalLimitError,
)


@pytest.fixture
def bank(clock) -> Bank:
    return Bank("Mudiwa Bank", clock=clock)


@pytest.fixture
def ronaldo(bank):
    return bank.add_customer("Ronaldo Mudiwa", "ronaldo@example.com")


@pytest.fixture
def amara(bank):
    return bank.add_customer("Amara Okafor", "amara@example.com")


@pytest.fixture
def current(bank, ronaldo) -> CurrentAccount:
    return bank.open_account(ronaldo.customer_id, "current", "500", overdraft_limit="100")


@pytest.fixture
def savings(bank, ronaldo) -> SavingsAccount:
    return bank.open_account(ronaldo.customer_id, "savings", "1000", max_withdrawals_per_month=1)


@pytest.fixture
def amara_current(bank, amara) -> CurrentAccount:
    return bank.open_account(amara.customer_id, "current", "20")


class TestCustomers:

    def test_ids_count_up(self, ronaldo, amara):
        assert (ronaldo.customer_id, amara.customer_id) == ("C0001", "C0002")

    def test_get_customer(self, bank, ronaldo):
        assert bank.get_customer("C0001") is ronaldo

    def test_unknown_customer(self, bank):
        with pytest.raises(CustomerNotFoundError):
            bank.get_customer("C9999")

    def test_same_email_in_any_case_is_refused(self, bank, ronaldo):
        with pytest.raises(DuplicateCustomerError):
            bank.add_customer("Someone Else", "RONALDO@Example.com")
        assert len(bank.customers) == 1

    def test_failed_add_does_not_use_up_an_id(self, bank, ronaldo):
        with pytest.raises(DuplicateCustomerError):
            bank.add_customer("Copy", "ronaldo@example.com")
        assert bank.add_customer("Next", "next@example.com").customer_id == "C0002"

    def test_bad_details(self, bank):
        with pytest.raises(ValidationError):
            bank.add_customer("Ronaldo", "not-an-email")


class TestOpeningAccounts:

    def test_numbers_count_up(self, current, savings):
        assert (current.account_number, savings.account_number) == ("10000001", "10000002")

    def test_right_type_and_options(self, current, savings):
        assert isinstance(current, CurrentAccount)
        assert current.overdraft_limit == Decimal("100.00")
        assert isinstance(savings, SavingsAccount)

    def test_owner_name_comes_from_customer(self, current):
        assert current.owner_name == "Ronaldo Mudiwa"

    def test_uses_the_banks_clock(self, current, clock):
        assert current.transactions[0].timestamp == clock.now

    def test_unknown_customer(self, bank):
        with pytest.raises(CustomerNotFoundError):
            bank.open_account("C9999")

    def test_unknown_type(self, bank, ronaldo):
        with pytest.raises(ValidationError, match="current, savings"):
            bank.open_account(ronaldo.customer_id, "crypto")

    def test_option_the_type_does_not_take(self, bank, ronaldo):
        with pytest.raises(ValidationError, match="Bad option"):
            bank.open_account(ronaldo.customer_id, "savings", overdraft_limit="100")

    def test_custom_number_generator(self, clock, ronaldo):
        bank = Bank("Test", SequentialAccountNumberGenerator(start=500), clock=clock)
        customer = bank.add_customer("R", "r@example.com")
        assert bank.open_account(customer.customer_id).account_number == "00000500"


class TestFindingAccounts:

    def test_get_account(self, bank, current):
        assert bank.get_account("10000001") is current

    def test_unknown_account(self, bank):
        with pytest.raises(AccountNotFoundError):
            bank.get_account("12345678")

    def test_not_found_errors_share_a_parent(self, bank):
        with pytest.raises(NotFoundError):
            bank.get_account("nope")
        with pytest.raises(NotFoundError):
            bank.get_customer("nope")

    def test_accounts_for(self, bank, ronaldo, amara, current, savings, amara_current):
        assert bank.accounts_for(ronaldo.customer_id) == [current, savings]
        assert bank.accounts_for(amara.customer_id) == [amara_current]

    def test_accounts_for_unknown_customer(self, bank):
        with pytest.raises(CustomerNotFoundError):
            bank.accounts_for("C9999")

    def test_owner_of(self, bank, ronaldo, current):
        assert bank.owner_of(current.account_number) is ronaldo

    def test_container_behaviour(self, bank, current, savings):
        assert len(bank) == 2
        assert "10000001" in bank and "99999999" not in bank
        assert list(bank) == [current, savings]


class TestClosing:

    def test_close_empty_account(self, bank, ronaldo):
        account = bank.open_account(ronaldo.customer_id)
        bank.close_account(account.account_number)
        assert not account.is_open
        assert account.account_number in bank  # kept on record

    def test_cannot_close_with_money_in(self, bank, current):
        with pytest.raises(ValidationError):
            bank.close_account(current.account_number)


class TestTransfer:

    def test_moves_money(self, bank, current, amara_current):
        bank.transfer(current.account_number, amara_current.account_number, "50")
        assert current.balance == Decimal("450.00")
        assert amara_current.balance == Decimal("70.00")

    def test_both_sides_in_history(self, bank, current, amara_current):
        out, money_in = bank.transfer(current.account_number, amara_current.account_number,
                                      "50", "Pizza money")
        assert out.kind is TransactionType.TRANSFER_OUT
        assert money_in.kind is TransactionType.TRANSFER_IN
        assert out.description == money_in.description == "Pizza money"

    def test_default_descriptions_name_the_other_account(self, bank, current, amara_current):
        out, money_in = bank.transfer(current.account_number, amara_current.account_number, "5")
        assert out.description == f"Transfer to {amara_current.account_number}"
        assert money_in.description == f"Transfer from {current.account_number}"

    def test_total_is_unchanged(self, bank, current, savings, amara_current):
        before = bank.total_deposits
        bank.transfer(current.account_number, amara_current.account_number, "123.45")
        assert bank.total_deposits == before

    def test_can_use_overdraft(self, bank, current, amara_current):
        bank.transfer(current.account_number, amara_current.account_number, "600")
        assert current.balance == Decimal("-100.00")

    def test_not_enough_money_changes_nothing(self, bank, current, amara_current):
        with pytest.raises(InsufficientFundsError):
            bank.transfer(current.account_number, amara_current.account_number, "600.01")
        assert current.balance == Decimal("500.00")
        assert amara_current.balance == Decimal("20.00")

    def test_savings_limit_counts_transfers(self, bank, savings, current):
        bank.transfer(savings.account_number, current.account_number, "10")
        with pytest.raises(WithdrawalLimitError):
            bank.transfer(savings.account_number, current.account_number, "10")

    def test_one_error_type_for_any_refusal(self, bank, savings, current):
        bank.transfer(savings.account_number, current.account_number, "10")
        with pytest.raises(WithdrawalError):
            bank.transfer(savings.account_number, current.account_number, "10")

    def test_same_account(self, bank, current):
        with pytest.raises(ValidationError):
            bank.transfer(current.account_number, current.account_number, "5")

    @pytest.mark.parametrize("bad", ["0", "-5", "lots"])
    def test_bad_amount(self, bank, current, amara_current, bad):
        with pytest.raises(ValidationError):
            bank.transfer(current.account_number, amara_current.account_number, bad)

    def test_unknown_accounts(self, bank, current):
        with pytest.raises(AccountNotFoundError):
            bank.transfer(current.account_number, "99999999", "5")
        with pytest.raises(AccountNotFoundError):
            bank.transfer("99999999", current.account_number, "5")

    def test_frozen_receiver_takes_nothing_from_sender(self, bank, current, amara_current):
        amara_current.freeze()
        with pytest.raises(AccountNotActiveError):
            bank.transfer(current.account_number, amara_current.account_number, "50")
        assert current.balance == Decimal("500.00")
        assert len(current.transactions) == 1

    def test_frozen_sender(self, bank, current, amara_current):
        current.freeze()
        with pytest.raises(AccountNotActiveError):
            bank.transfer(current.account_number, amara_current.account_number, "50")


class BrokenAccount(CurrentAccount):
    """An account whose incoming transfers always fail, to test the refund."""

    ACCOUNT_TYPE = "broken"

    def receive_transfer(self, amount, from_account, description=None):
        raise RuntimeError("Something went wrong on the receiving side")


class TestOpenForNewTypes:
    """New account types plug in without changing the Bank."""

    def test_register_and_open(self, bank, ronaldo):
        class StudentAccount(CurrentAccount):
            ACCOUNT_TYPE = "student"

        bank.register_account_type(StudentAccount)
        account = bank.open_account(ronaldo.customer_id, "student", "10")
        assert isinstance(account, StudentAccount)
        assert "student" in bank.account_types

    def test_only_accounts_can_be_registered(self, bank):
        with pytest.raises(ValidationError):
            bank.register_account_type(str)
        with pytest.raises(ValidationError):
            bank.register_account_type(int)

    def test_failed_delivery_refunds_the_sender(self, bank, ronaldo, current):
        bank.register_account_type(BrokenAccount)
        broken = bank.open_account(ronaldo.customer_id, "broken")
        with pytest.raises(RuntimeError):
            bank.transfer(current.account_number, broken.account_number, "50")
        assert current.balance == Decimal("500.00")
        assert current.transactions[-1].description == "Transfer reversed"


def test_total_deposits_counts_overdrafts_as_negative(bank, current, amara_current):
    current.withdraw("550")
    assert bank.total_deposits == Decimal("-30.00")


def test_blank_bank_name():
    with pytest.raises(ValidationError):
        Bank("  ")


def test_repr(bank, ronaldo, current):
    assert repr(bank) == "Bank('Mudiwa Bank', customers=1, accounts=1)"
