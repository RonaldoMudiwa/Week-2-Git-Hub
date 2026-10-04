"""Tests for saving and loading the bank.

tmp_path gives each test its own empty folder, so real data is never touched.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from banking import (
    AccountStatus,
    Bank,
    BankRepository,
    CombinedFees,
    CurrentAccount,
    DuplicateCustomerError,
    FlatMonthlyFee,
    InMemoryBankRepository,
    JSONBankRepository,
    OverdraftFee,
    StorageError,
    TieredInterest,
    Transaction,
    TransactionType,
    ValidationError,
)

D = Decimal


@pytest.fixture
def bank(clock) -> Bank:
    """A bank with a bit of everything in it."""
    bank = Bank("Mudiwa Bank", clock=clock)
    ronaldo = bank.add_customer("Ronaldo Mudiwa", "ronaldo@example.com")
    amara = bank.add_customer("Amara Okafor", "amara@example.com")

    current = bank.open_account(ronaldo.customer_id, "current", "250", overdraft_limit="200",
                                fee_policy=CombinedFees(FlatMonthlyFee("3"), OverdraftFee("24")))
    savings = bank.open_account(ronaldo.customer_id, "savings", "1000", interest_rate="4.5",
                                max_withdrawals_per_month=2)
    amara_savings = bank.open_account(
        amara.customer_id, "savings", "6000",
        interest_policy=TieredInterest([("1000", "2"), (None, "5")]))

    current.deposit("1850", "Wages")
    bank.transfer(current.account_number, savings.account_number, "300", "Monthly saving")
    bank.transfer(savings.account_number, current.account_number, "50")
    bank.run_month_end()
    amara_savings.freeze()
    return bank


@pytest.fixture
def path(tmp_path):
    return tmp_path / "bank.json"


@pytest.fixture
def repo(path, clock) -> JSONBankRepository:
    return JSONBankRepository(path, clock=clock)


def write(path, document) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


class TestRoundTrip:
    """Whatever goes in must come back exactly the same."""

    @pytest.fixture
    def loaded(self, bank, repo) -> Bank:
        repo.save(bank)
        return repo.load()

    def test_nothing_saved_yet(self, repo):
        assert repo.load() is None

    def test_name_and_totals(self, bank, loaded):
        assert loaded.name == bank.name
        assert loaded.total_deposits == bank.total_deposits

    def test_customers(self, bank, loaded):
        assert [c.to_dict() for c in loaded.customers] == [c.to_dict() for c in bank.customers]

    def test_owners(self, bank, loaded):
        for account in bank:
            number = account.account_number
            assert loaded.owner_of(number) == bank.owner_of(number)

    def test_every_history_line(self, bank, loaded):
        for account in bank:
            assert loaded.get_account(account.account_number).transactions == account.transactions

    def test_account_types_and_settings(self, loaded):
        current, savings, amara_savings = list(loaded)
        assert isinstance(current, CurrentAccount)
        assert current.overdraft_limit == D("200.00")
        assert savings.interest_rate == D("4.50")
        assert savings.max_withdrawals_per_month == 2
        assert isinstance(amara_savings.interest_policy, TieredInterest)

    def test_rules_still_work_the_same(self, bank, loaded):
        for account in bank:
            again = loaded.get_account(account.account_number)
            for balance in ("-150", "0", "2500"):
                assert again.fee_policy.monthly_fee(D(balance)) == \
                    account.fee_policy.monthly_fee(D(balance))
                assert again.interest_policy.monthly_interest(D(balance)) == \
                    account.interest_policy.monthly_interest(D(balance))

    def test_status(self, loaded):
        assert loaded.get_account("10000003").status is AccountStatus.FROZEN

    def test_month_end_is_remembered(self, loaded):
        """Loading must not let this month's interest be paid twice."""
        assert loaded.run_month_end() == {}

    def test_savings_withdrawal_count_is_remembered(self, loaded):
        assert loaded.get_account("10000002").withdrawals_this_month == 1

    def test_new_account_numbers_carry_on(self, loaded):
        account = loaded.open_account("C0001", "current")
        assert account.account_number == "10000004"

    def test_new_customer_ids_carry_on(self, loaded):
        assert loaded.add_customer("New", "new@example.com").customer_id == "C0003"

    def test_duplicate_emails_still_caught(self, loaded):
        with pytest.raises(DuplicateCustomerError):
            loaded.add_customer("Copy", "ronaldo@example.com")

    def test_loaded_bank_keeps_working(self, loaded, clock):
        loaded.transfer("10000001", "10000002", "10")
        clock.advance(days=31)
        assert "10000002" in loaded.run_month_end()

    def test_empty_bank(self, repo, clock):
        repo.save(Bank("Empty", clock=clock))
        loaded = repo.load()
        assert len(loaded) == 0 and loaded.customers == ()


class TestFile:

    def test_save_creates_the_file_and_folders(self, bank, tmp_path):
        repo = JSONBankRepository(tmp_path / "a" / "b" / "bank.json")
        repo.save(bank)
        assert repo.path.exists()

    def test_amounts_saved_as_text(self, bank, repo, path):
        repo.save(bank)
        first_line = json.loads(path.read_text())["bank"]["accounts"][0]["transactions"][0]
        assert first_line["amount"] == "250.00"

    def test_has_version(self, bank, repo, path):
        repo.save(bank)
        assert json.loads(path.read_text())["version"] == 1

    def test_save_replaces_old_contents(self, bank, repo, clock):
        repo.save(bank)
        repo.save(Bank("Other", clock=clock))
        assert repo.load().name == "Other"

    def test_no_temp_files_left(self, bank, repo, tmp_path):
        repo.save(bank)
        repo.save(bank)
        assert [p.name for p in tmp_path.iterdir()] == ["bank.json"]


class TestBadFiles:
    """A damaged file gives one clear StorageError."""

    def test_not_json(self, repo, path):
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(StorageError, match="not valid JSON"):
            repo.load()

    @pytest.mark.parametrize("document, message", [
        ([], "JSON object"),
        ({"version": 99, "bank": {}}, "version"),
        ({"version": 1}, "no saved bank"),
    ])
    def test_wrong_shape(self, repo, path, document, message):
        write(path, document)
        with pytest.raises(StorageError, match=message):
            repo.load()

    def _saved(self, bank, repo, path):
        repo.save(bank)
        return json.loads(path.read_text())

    def test_edited_balance_is_caught(self, bank, repo, path):
        """Someone changing a number in the file can't create money."""
        document = self._saved(bank, repo, path)
        document["bank"]["accounts"][0]["transactions"][0]["balance_after"] = "1000000.00"
        write(path, document)
        with pytest.raises(StorageError, match="doesn't add up"):
            repo.load()

    def test_unknown_account_type(self, bank, repo, path):
        document = self._saved(bank, repo, path)
        document["bank"]["accounts"][0]["type"] = "crypto"
        write(path, document)
        with pytest.raises(StorageError, match="crypto"):
            repo.load()

    def test_unknown_owner(self, bank, repo, path):
        document = self._saved(bank, repo, path)
        document["bank"]["accounts"][0]["owner"] = "C9999"
        write(path, document)
        with pytest.raises(StorageError, match="unknown owner"):
            repo.load()

    def test_duplicate_account(self, bank, repo, path):
        document = self._saved(bank, repo, path)
        document["bank"]["accounts"].append(document["bank"]["accounts"][0])
        write(path, document)
        with pytest.raises(StorageError, match="saved twice"):
            repo.load()

    def test_unknown_rule_type(self, bank, repo, path):
        document = self._saved(bank, repo, path)
        document["bank"]["accounts"][0]["fee_policy"] = {"type": "mystery_fee"}
        write(path, document)
        with pytest.raises(StorageError, match="mystery_fee"):
            repo.load()

    def test_bad_customer_email(self, bank, repo, path):
        document = self._saved(bank, repo, path)
        document["bank"]["customers"][0]["email"] = "not an email"
        write(path, document)
        with pytest.raises(StorageError):
            repo.load()

    def test_missing_field(self, bank, repo, path):
        document = self._saved(bank, repo, path)
        del document["bank"]["accounts"][0]["owner_name"]
        write(path, document)
        with pytest.raises(StorageError, match="owner_name"):
            repo.load()

    def test_original_reason_is_kept(self, bank, repo, path):
        document = self._saved(bank, repo, path)
        document["bank"]["accounts"][0]["type"] = "crypto"
        write(path, document)
        with pytest.raises(StorageError) as caught:
            repo.load()
        assert isinstance(caught.value.__cause__, ValidationError)


class TestCustomAccountTypes:

    def test_extra_types_can_be_loaded(self, path, clock):
        class StudentAccount(CurrentAccount):
            ACCOUNT_TYPE = "student"

        bank = Bank("Uni Bank", clock=clock)
        bank.register_account_type(StudentAccount)
        customer = bank.add_customer("Student", "s@example.com")
        bank.open_account(customer.customer_id, "student", "20")

        JSONBankRepository(path).save(bank)
        with pytest.raises(StorageError):
            JSONBankRepository(path).load()  # doesn't know about students
        loaded = JSONBankRepository(path, extra_account_types=(StudentAccount,)).load()
        assert isinstance(loaded.get_account("10000001"), StudentAccount)


class TestInMemory:

    def test_round_trip(self, bank, clock):
        repo = InMemoryBankRepository(clock)
        assert repo.load() is None
        repo.save(bank)
        assert repo.load().total_deposits == bank.total_deposits

    def test_saved_copy_does_not_change(self, bank, clock):
        repo = InMemoryBankRepository(clock)
        repo.save(bank)
        bank.get_account("10000001").deposit("1000")
        assert repo.load().total_deposits != bank.total_deposits


class TestPieces:
    """Each part can save and load itself."""

    def test_transaction(self, bank):
        line = bank.get_account("10000001").transactions[0]
        assert Transaction.from_dict(line.to_dict()) == line

    def test_transaction_bad_kind(self, bank):
        data = bank.get_account("10000001").transactions[0].to_dict()
        data["kind"] = "robbery"
        with pytest.raises(ValidationError):
            Transaction.from_dict(data)

    def test_transaction_kinds_survive(self, bank):
        kinds = {t.kind for a in bank for t in a.transactions}
        assert {TransactionType.INTEREST, TransactionType.FEE,
                TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT} <= kinds


def test_base_class_cannot_be_created():
    with pytest.raises(TypeError):
        BankRepository()
