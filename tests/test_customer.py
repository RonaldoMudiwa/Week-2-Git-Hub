"""Tests for customers."""

import pytest

from banking import Customer, ValidationError


class TestCustomer:

    def test_details(self):
        customer = Customer("C0001", "Ronaldo Mudiwa", "ronaldo@example.com")
        assert customer.customer_id == "C0001"
        assert customer.name == "Ronaldo Mudiwa"
        assert str(customer) == "Ronaldo Mudiwa (C0001)"

    def test_email_is_lower_cased_and_trimmed(self):
        assert Customer("C1", "R", "  Ronaldo@Mail.COM ").email == "ronaldo@mail.com"

    @pytest.mark.parametrize("bad", ["ronaldo", "ronaldo@", "@mail.com", "a b@mail.com",
                                     "ronaldo@mail", "", 42])
    def test_bad_email(self, bad):
        with pytest.raises(ValidationError):
            Customer("C1", "Ronaldo", bad)

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_bad_name(self, bad):
        with pytest.raises(ValidationError):
            Customer("C1", bad, "r@mail.com")

    def test_blank_id(self):
        with pytest.raises(ValidationError):
            Customer(" ", "Ronaldo", "r@mail.com")

    def test_details_can_be_updated_and_are_checked(self):
        customer = Customer("C1", "Ronaldo", "r@mail.com")
        customer.email = "new@mail.com"
        with pytest.raises(ValidationError):
            customer.email = "not an email"
        assert customer.email == "new@mail.com"

    def test_id_cannot_be_changed(self):
        with pytest.raises(AttributeError):
            Customer("C1", "Ronaldo", "r@mail.com").customer_id = "C2"

    def test_equal_by_id(self):
        assert Customer("C1", "A", "a@mail.com") == Customer("C1", "B", "b@mail.com")
        assert len({Customer("C1", "A", "a@mail.com"), Customer("C1", "A", "a@mail.com")}) == 1
