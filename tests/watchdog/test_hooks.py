"""Boot/teardown hook registration (interfaces only; no graph implementations)."""

import pytest

from cascade.watchdog.hooks import (
    invoke_boot,
    register_boot_hook,
    register_teardown_hook,
)


def test_register_boot_and_teardown_accept_epic_feature_task() -> None:
    booted: list[tuple[str, str]] = []
    torn: list[tuple[str, str]] = []

    register_boot_hook("epic", lambda wid: booted.append(("epic", wid)))
    register_boot_hook("feature", lambda wid: booted.append(("feature", wid)))
    register_boot_hook("task", lambda wid: booted.append(("task", wid)))

    register_teardown_hook("epic", lambda wid: torn.append(("epic", wid)))
    register_teardown_hook("feature", lambda wid: torn.append(("feature", wid)))
    register_teardown_hook("task", lambda wid: torn.append(("task", wid)))

    invoke_boot("epic", "epic_001")
    invoke_boot("feature", "feat_001")
    invoke_boot("task", "task_001")

    assert booted == [
        ("epic", "epic_001"),
        ("feature", "feat_001"),
        ("task", "task_001"),
    ]
    assert torn == []


def test_invoke_boot_runs_hooks_in_registration_order() -> None:
    seen: list[str] = []

    register_boot_hook("task", lambda wid: seen.append(f"a:{wid}"))
    register_boot_hook("task", lambda wid: seen.append(f"b:{wid}"))

    invoke_boot("task", "task_007")

    assert seen == ["a:task_007", "b:task_007"]


def test_unknown_tier_raises() -> None:
    with pytest.raises(ValueError, match="unknown tier"):
        register_boot_hook("graph", lambda _wid: None)
    with pytest.raises(ValueError, match="unknown tier"):
        register_teardown_hook("boss", lambda _wid: None)
