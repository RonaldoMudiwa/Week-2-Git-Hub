"""Shared test helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


class FakeClock:
    """A clock the tests control, so dates don't depend on when tests run."""

    def __init__(self, start: datetime = datetime(2026, 10, 1, 9, 0)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        """Move time forward, e.g. clock.advance(days=31)."""
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
