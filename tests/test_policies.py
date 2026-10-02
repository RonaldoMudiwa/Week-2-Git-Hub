"""Tests for the interest and fee rules on their own, without any account."""

from decimal import Decimal

import pytest

from banking import (
    CombinedFees,
    FeePolicy,
    FlatMonthlyFee,
    FlatRateInterest,
    InterestPolicy,
    NoFee,
    NoInterest,
    OverdraftFee,
    TieredInterest,
    ValidationError,
)

D = Decimal


class TestNoInterestOrFee:

    @pytest.mark.parametrize("balance", ["-50", "0", "1000000"])
    def test_always_zero(self, balance):
        assert NoInterest().monthly_interest(D(balance)) == D("0.00")
        assert NoFee().monthly_fee(D(balance)) == D("0.00")


class TestFlatRateInterest:

    def test_one_month_of_the_yearly_rate(self):
        assert FlatRateInterest("4.8").monthly_interest(D("1000")) == D("4.00")

    def test_rounds_to_the_nearest_penny(self):
        # 123.45 * 3% / 12 = 0.308625
        assert FlatRateInterest("3").monthly_interest(D("123.45")) == D("0.31")

    @pytest.mark.parametrize("balance", ["0", "-200"])
    def test_nothing_on_zero_or_negative(self, balance):
        assert FlatRateInterest("5").monthly_interest(D(balance)) == D("0.00")

    def test_zero_rate(self):
        assert FlatRateInterest("0").monthly_interest(D("1000")) == D("0.00")

    @pytest.mark.parametrize("bad", ["-1", "100.01", "lots", 4.5])
    def test_bad_rate(self, bad):
        with pytest.raises(ValidationError):
            FlatRateInterest(bad)


class TestTieredInterest:

    @pytest.fixture
    def tiers(self):
        return TieredInterest([("1000", "2"), ("5000", "3"), (None, "4")])

    @pytest.mark.parametrize("balance, expected", [
        ("500", "0.83"),      # 500 at 2%
        ("1000", "1.67"),     # exactly the first band
        ("3000", "6.67"),     # 1000 at 2% + 2000 at 3%
        ("10000", "28.33"),   # 1000 at 2% + 4000 at 3% + 5000 at 4%
        ("0", "0.00"),
        ("-100", "0.00"),
    ])
    def test_each_slice_earns_its_own_rate(self, tiers, balance, expected):
        assert tiers.monthly_interest(D(balance)) == D(expected)

    def test_last_band_can_have_a_limit(self):
        capped = TieredInterest([("1000", "6")])
        assert capped.monthly_interest(D("5000")) == D("5.00")  # only the first 1000 earns

    def test_needs_a_band(self):
        with pytest.raises(ValidationError):
            TieredInterest([])

    def test_only_last_band_can_be_open_ended(self):
        with pytest.raises(ValidationError):
            TieredInterest([(None, "2"), ("1000", "3")])

    def test_limits_must_go_up(self):
        with pytest.raises(ValidationError):
            TieredInterest([("1000", "2"), ("500", "3")])

    def test_bad_rate_in_a_band(self):
        with pytest.raises(ValidationError):
            TieredInterest([(None, "-1")])


class TestFlatMonthlyFee:

    @pytest.mark.parametrize("balance", ["-50", "0", "1000"])
    def test_same_whatever_the_balance(self, balance):
        assert FlatMonthlyFee("3").monthly_fee(D(balance)) == D("3.00")

    def test_negative_fee(self):
        with pytest.raises(ValidationError):
            FlatMonthlyFee("-1")


class TestOverdraftFee:

    def test_charged_on_what_is_borrowed(self):
        assert OverdraftFee("24").monthly_fee(D("-500")) == D("10.00")

    @pytest.mark.parametrize("balance", ["0", "250"])
    def test_nothing_when_not_overdrawn(self, balance):
        assert OverdraftFee("24", minimum="5").monthly_fee(D(balance)) == D("0.00")

    def test_minimum_charge(self):
        assert OverdraftFee("24", minimum="2").monthly_fee(D("-10")) == D("2.00")

    def test_minimum_only_when_bigger(self):
        assert OverdraftFee("24", minimum="2").monthly_fee(D("-1000")) == D("20.00")

    def test_bad_values(self):
        with pytest.raises(ValidationError):
            OverdraftFee("-5")
        with pytest.raises(ValidationError):
            OverdraftFee("20", minimum="-1")


class TestCombinedFees:

    def test_adds_them_up(self):
        fees = CombinedFees(FlatMonthlyFee("3"), OverdraftFee("24"))
        assert fees.monthly_fee(D("-500")) == D("13.00")
        assert fees.monthly_fee(D("500")) == D("3.00")

    def test_is_a_fee_policy_itself(self):
        assert isinstance(CombinedFees(NoFee()), FeePolicy)

    @pytest.mark.parametrize("bad", [(), (NoInterest(),), ("£3",)])
    def test_only_fee_policies(self, bad):
        with pytest.raises(ValidationError):
            CombinedFees(*bad)


def test_base_classes_cannot_be_created():
    with pytest.raises(TypeError):
        InterestPolicy()
    with pytest.raises(TypeError):
        FeePolicy()


def test_repr_shows_the_settings():
    assert repr(TieredInterest([("1000", "2"), (None, "4")])) == \
        "TieredInterest([('1000.00', '2.00'), (None, '4.00')])"
    assert repr(OverdraftFee("24", minimum="2")) == "OverdraftFee('24.00', minimum='2.00')"
