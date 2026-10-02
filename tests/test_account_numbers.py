"""Tests for account number generators."""

import pytest

from banking import AccountNumberGenerator, SequentialAccountNumberGenerator, ValidationError


class TestSequential:

    def test_counts_up(self):
        numbers = SequentialAccountNumberGenerator()
        assert [numbers.next_number() for _ in range(3)] == ["10000001", "10000002", "10000003"]

    def test_pads_to_eight_digits(self):
        assert SequentialAccountNumberGenerator(start=42).next_number() == "00000042"

    def test_runs_out(self):
        numbers = SequentialAccountNumberGenerator(start=99999999)
        assert numbers.next_number() == "99999999"
        with pytest.raises(ValidationError):
            numbers.next_number()

    @pytest.mark.parametrize("bad", [0, -1, 100000000, 1.5, True, "1"])
    def test_bad_start(self, bad):
        with pytest.raises(ValidationError):
            SequentialAccountNumberGenerator(start=bad)


def test_base_class_cannot_be_created():
    with pytest.raises(TypeError):
        AccountNumberGenerator()
