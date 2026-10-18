"""Isolate watchdog tests from boot-hook registration leakage."""

from __future__ import annotations

import pytest

from cascade.watchdog.hooks import clear_hooks


@pytest.fixture(autouse=True)
def _clear_watchdog_hooks() -> None:
    clear_hooks()
    yield
    clear_hooks()
