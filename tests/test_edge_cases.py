"""The less common paths: damaged saved data, failed writes, and the small
helpers that the main tests don't reach.
"""

from __future__ import annotations

import os
import runpy
import sys
from decimal import Decimal

import pytest

from banking import (
    Account,
    Bank,
    CombinedFees,
    CurrentAccount,
    Customer,
    FlatMonthlyFee,
    FlatRateInterest,
    JSONBankRepository,
    NoFee,
    NoInterest,
    OverdraftFee,
    StorageError,
    Transaction,
    ValidationError,
)
from banking.cli import main
from banking.policies import policy_from_dict, register_policy

D = Decimal


class PlainAccount(Account):
    """An account type that adds no settings of its own."""

    ACCOUNT_TYPE = "plain"

    @property
    def available_to_withdraw(self) -> Decimal:
        return self.balance


class TestRunningTheProgram:
    def test_main_returns_the_exit_code(self, tmp_path, capsys):
        assert main(["--file", str(tmp_path / "bank.json"), "customers"]) == 0
        assert "No customers yet." in capsys.readouterr().out

    def test_python_dash_m_banking(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["banking", "--file", str(tmp_path / "b.json"), "accounts"])
        with pytest.raises(SystemExit) as stopped:
            runpy.run_module("banking", run_name="__main__")
        assert stopped.value.code == 0
        assert "No accounts yet." in capsys.readouterr().out


class TestDamagedSavedData:
    def test_account_with_an_unknown_status(self):
        data = CurrentAccount("10000001", "Ronaldo", "10").to_dict()
        data["status"] = "sleeping"
        with pytest.raises(ValidationError, match="bad value"):
            CurrentAccount.from_dict(data)

    def test_bank_without_a_name(self):
        with pytest.raises(ValidationError, match="missing"):
            Bank.from_dict({"customers": [], "accounts": []})

    def test_customer_saved_twice(self):
        customer = Customer("C0001", "Ronaldo", "r@example.com").to_dict()
        with pytest.raises(ValidationError, match="saved twice"):
            Bank.from_dict({"name": "Mudiwa Bank", "customers": [customer, customer]})

    def test_customer_missing_an_email(self):
        with pytest.raises(ValidationError, match="email"):
            Customer.from_dict({"customer_id": "C0001", "name": "Ronaldo"})

    def test_transaction_missing_a_field(self):
        data = CurrentAccount("10000001", "Ronaldo", "10").transactions[0].to_dict()
        del data["amount"]
        with pytest.raises(ValidationError, match="amount"):
            Transaction.from_dict(data)

    def test_rule_without_a_type(self):
        with pytest.raises(ValidationError, match="type"):
            policy_from_dict({"settings": {}})

    def test_rule_with_the_wrong_settings(self):
        with pytest.raises(ValidationError, match="FlatMonthlyFee"):
            policy_from_dict({"type": "flat_monthly_fee", "settings": {"price": "3"}})


class TestFileProblems:
    def test_save_fails_when_the_folder_is_really_a_file(self, tmp_path):
        blocker = tmp_path / "not_a_folder"
        blocker.write_text("in the way", encoding="utf-8")
        repository = JSONBankRepository(blocker / "bank.json")
        with pytest.raises(StorageError, match="Could not save"):
            repository.save(Bank("Mudiwa Bank"))

    def test_load_fails_when_the_path_is_a_folder(self, tmp_path):
        with pytest.raises(StorageError, match="Could not read"):
            JSONBankRepository(tmp_path).load()

    def test_failed_write_keeps_the_old_file_and_cleans_up(self, tmp_path, monkeypatch):
        path = tmp_path / "bank.json"
        repository = JSONBankRepository(path)
        repository.save(Bank("Old Bank"))

        def broken_replace(source, target):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", broken_replace)
        with pytest.raises(StorageError, match="disk full"):
            repository.save(Bank("New Bank"))
        monkeypatch.undo()

        assert repository.load().name == "Old Bank"
        assert [p.name for p in tmp_path.iterdir()] == ["bank.json"]  # no temp file left

    def test_repr_shows_the_path(self, tmp_path):
        assert "bank.json" in repr(JSONBankRepository(tmp_path / "bank.json"))


class TestSmallHelpers:
    def test_account_type_with_no_extra_settings(self):
        bank = Bank("Mudiwa Bank")
        bank.register_account_type(PlainAccount)
        customer = bank.add_customer("Ronaldo", "r@example.com")
        account = bank.open_account(customer.customer_id, "plain", "5")
        assert account.settings() == {}
        loaded = Bank.from_dict(bank.to_dict(), extra_account_types=(PlainAccount,))
        assert loaded.get_account(account.account_number).balance == D("5.00")

    def test_accounts_and_customers_never_equal_other_things(self):
        assert CurrentAccount("10000001", "Ronaldo") != "10000001"
        assert Customer("C0001", "Ronaldo", "r@example.com") != "C0001"

    def test_customer_repr(self):
        assert repr(Customer("C0001", "Ronaldo", "r@example.com")) == \
            "Customer('C0001', 'Ronaldo', 'r@example.com')"

    @pytest.mark.parametrize("rule, text", [
        (NoInterest(), "NoInterest()"),
        (FlatRateInterest("4.5"), "FlatRateInterest('4.50')"),
        (NoFee(), "NoFee()"),
        (FlatMonthlyFee("3"), "FlatMonthlyFee('3.00')"),
    ])
    def test_rule_reprs(self, rule, text):
        assert repr(rule) == text

    def test_combined_fees_repr_lists_each_rule(self):
        text = repr(CombinedFees(FlatMonthlyFee("3"), OverdraftFee("24")))
        assert text.startswith("CombinedFees(FlatMonthlyFee('3.00'), OverdraftFee(")

    def test_rule_names_must_be_unique(self):
        with pytest.raises(ValueError, match="already used"):
            @register_policy("flat_rate_interest")
            class Copy(FlatRateInterest):
                pass
