"""Tests for transaction records."""

import dataclasses
from datetime import datetime
from decimal import Decimal

import pytest

from banking import Transaction, TransactionType


def make(kind=TransactionType.DEPOSIT, amount="50.00", balance="150.00"):
    return Transaction(kind, Decimal(amount), Decimal(balance), "Wages",
                       datetime(2026, 10, 2, 14, 5))


class TestTransactionType:

    @pytest.mark.parametrize("kind", [TransactionType.DEPOSIT, TransactionType.TRANSFER_IN,
                                      TransactionType.INTEREST])
    def test_credits(self, kind):
        assert kind.is_credit

    @pytest.mark.parametrize("kind", [TransactionType.WITHDRAWAL, TransactionType.TRANSFER_OUT,
                                      TransactionType.FEE])
    def test_debits(self, kind):
        assert not kind.is_credit

    def test_label(self):
        assert TransactionType.TRANSFER_IN.label == "Transfer In"


class TestTransaction:

    def test_signed_amount_for_money_in(self):
        assert make().signed_amount == Decimal("50.00")

    def test_signed_amount_for_money_out(self):
        assert make(TransactionType.WITHDRAWAL).signed_amount == Decimal("-50.00")

    def test_cannot_be_changed(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            make().amount = Decimal("1000")

    def test_each_gets_its_own_id(self):
        assert make().transaction_id != make().transaction_id

    def test_summary_line(self):
        line = make().summary_line()
        assert line.startswith("2026-10-02 14:05")
        assert "+£50.00" in line and "£150.00" in line and line.endswith("Wages")
