"""A person who banks with us."""

from __future__ import annotations

import re
from typing import Any

from .exceptions import ValidationError

# Simple on purpose: something@something.something. Fully checking an email
# address is famously hard, and the real test is whether mail arrives.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Customer:
    """A customer's personal details.

    Only holds who the person is. Which accounts they own is the Bank's job,
    so this class has just one reason to change.
    """

    def __init__(self, customer_id: str, name: str, email: str) -> None:
        if not isinstance(customer_id, str) or not customer_id.strip():
            raise ValidationError("Customer id can't be blank.")
        self._customer_id = customer_id.strip()
        self.name = name
        self.email = email

    @property
    def customer_id(self) -> str:
        return self._customer_id

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("Name can't be blank.")
        self._name = " ".join(value.split())

    @property
    def email(self) -> str:
        return self._email

    @email.setter
    def email(self, value: str) -> None:
        if not isinstance(value, str):
            raise ValidationError("Email must be text.")
        # Stored in lower case so "Ronaldo@Mail.com" and "ronaldo@mail.com" match.
        cleaned = value.strip().lower()
        if not EMAIL_PATTERN.match(cleaned):
            raise ValidationError(f"{value!r} doesn't look like an email address.")
        self._email = cleaned

    def to_dict(self) -> dict[str, Any]:
        return {"customer_id": self._customer_id, "name": self._name, "email": self._email}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Customer":
        """Rebuild a customer. The usual checks run again, so bad data is caught."""
        try:
            return cls(data["customer_id"], data["name"], data["email"])
        except KeyError as error:
            raise ValidationError(f"Customer is missing {error}.") from error

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Customer):
            return NotImplemented
        return self._customer_id == other._customer_id

    def __hash__(self) -> int:
        return hash(self._customer_id)

    def __repr__(self) -> str:
        return f"Customer({self._customer_id!r}, {self._name!r}, {self._email!r})"

    def __str__(self) -> str:
        return f"{self._name} ({self._customer_id})"
