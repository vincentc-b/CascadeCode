"""Boot and teardown hook registries. Graph implementations are out of scope."""

from __future__ import annotations

from collections.abc import Callable

Hook = Callable[[str], None]
_TIERS = ("epic", "feature", "task")
_boot: dict[str, list[Hook]] = {tier: [] for tier in _TIERS}
_teardown: dict[str, list[Hook]] = {tier: [] for tier in _TIERS}


def register_boot_hook(tier: str, fn: Hook) -> None:
    """Register `fn(work_id)` to run after a successful dispatch of `tier`."""

    _bucket(_boot, tier).append(fn)


def register_teardown_hook(tier: str, fn: Hook) -> None:
    """Register `fn(work_id)` to run on tier teardown via ``invoke_teardown``."""

    _bucket(_teardown, tier).append(fn)


def invoke_boot(tier: str, work_id: str) -> None:
    for fn in list(_bucket(_boot, tier)):
        fn(work_id)


def invoke_teardown(tier: str, work_id: str) -> None:
    for fn in list(_bucket(_teardown, tier)):
        fn(work_id)


def clear_hooks() -> None:
    for tier in _TIERS:
        _boot[tier].clear()
        _teardown[tier].clear()


def _bucket(store: dict[str, list[Hook]], tier: str) -> list[Hook]:
    if tier not in store:
        raise ValueError(f"unknown tier: {tier}")
    return store[tier]
