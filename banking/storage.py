"""Saving the bank between runs of the program.

The rest of the app only uses BankRepository, so the JSON file could be
swapped for a database later without changing anything else.
"""

from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .account import Account, Clock
from .bank import Bank
from .exceptions import BankError, StorageError

# Change this if the file layout ever changes.
FILE_FORMAT_VERSION = 1


class BankRepository(ABC):
    """Anything that can save and load a whole bank."""

    @abstractmethod
    def save(self, bank: Bank) -> None:
        """Replace whatever was saved with this bank. Raises StorageError on failure."""

    @abstractmethod
    def load(self) -> Bank | None:
        """Return the saved bank, or None if nothing has been saved yet.

        Raises:
            StorageError: If the saved data is damaged.
        """


class InMemoryBankRepository(BankRepository):
    """Keeps the bank in memory instead of a file. Used in tests.

    It still stores plain data, not the objects, so it behaves like a real
    file: changing the bank after saving doesn't change the saved copy.
    """

    def __init__(self, clock: Clock | None = None,
                 extra_account_types: tuple[type[Account], ...] = ()) -> None:
        self._clock = clock
        self._extra_types = extra_account_types
        self._saved: str | None = None

    def save(self, bank: Bank) -> None:
        self._saved = json.dumps(bank.to_dict())

    def load(self) -> Bank | None:
        if self._saved is None:
            return None
        return Bank.from_dict(json.loads(self._saved), self._clock, self._extra_types)


class JSONBankRepository(BankRepository):
    """Saves the bank to a JSON file.

    File layout: {"version": 1, "bank": {...}}
    """

    def __init__(self, file_path: str | Path, clock: Clock | None = None,
                 extra_account_types: tuple[type[Account], ...] = ()) -> None:
        self._path = Path(file_path)
        self._clock = clock
        self._extra_types = extra_account_types

    @property
    def path(self) -> Path:
        return self._path

    def save(self, bank: Bank) -> None:
        """Write the whole bank to the file.

        Written to a temporary file first and then swapped in, so a crash
        half way through leaves the old file whole.
        """
        text = json.dumps({"version": FILE_FORMAT_VERSION, "bank": bank.to_dict()},
                          indent=2, ensure_ascii=False)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._write_safely(text)
        except OSError as error:
            raise StorageError(f"Could not save to {self._path}: {error}") from error

    def load(self) -> Bank | None:
        """Read the file. No file yet means nothing has been saved, so None."""
        if not self._path.exists():
            return None
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError as error:
            raise StorageError(f"Could not read {self._path}: {error}") from error
        except json.JSONDecodeError as error:
            raise StorageError(f"{self._path} is not valid JSON (line {error.lineno}).") from error

        bank_data = self._unwrap(document)
        try:
            return Bank.from_dict(bank_data, self._clock, self._extra_types)
        except BankError as error:
            # One error type for the caller, with the real cause kept.
            raise StorageError(f"{self._path} is damaged: {error}") from error

    def _unwrap(self, document: Any) -> dict[str, Any]:
        """Check the outer shape of the file and return the bank part."""
        if not isinstance(document, dict):
            raise StorageError(f"{self._path} should hold a JSON object at the top.")
        if document.get("version") != FILE_FORMAT_VERSION:
            raise StorageError(
                f"{self._path} is format version {document.get('version')!r}; "
                f"this program reads version {FILE_FORMAT_VERSION}."
            )
        bank_data = document.get("bank")
        if not isinstance(bank_data, dict):
            raise StorageError(f"{self._path} has no saved bank in it.")
        return bank_data

    def _write_safely(self, text: str) -> None:
        # Same folder, because os.replace only swaps cleanly on one drive.
        handle, temp_name = tempfile.mkstemp(dir=self._path.parent, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
                temp_file.write(text)
            os.replace(temp_name, self._path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._path)!r})"
