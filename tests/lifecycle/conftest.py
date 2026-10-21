"""Pytest fixtures for disposable lifecycle sandbox scenarios."""

from __future__ import annotations

import pytest

from tests.lifecycle.scenario import (
    LifecycleScenario,
    LifecycleWarRoom,
    quiet_lifecycle_dispatch,
    seed_lifecycle_scenario,
    start_lifecycle_war_room,
    teardown_lifecycle_scenario,
)


@pytest.fixture
def lifecycle_scenario(tmp_path, monkeypatch: pytest.MonkeyPatch) -> LifecycleScenario:
    quiet_lifecycle_dispatch(monkeypatch)
    scenario = seed_lifecycle_scenario(tmp_path)
    yield scenario
    teardown_lifecycle_scenario(scenario.root)


@pytest.fixture
def lifecycle_war_room(lifecycle_scenario: LifecycleScenario) -> LifecycleWarRoom:
    gen = start_lifecycle_war_room(lifecycle_scenario)
    handle = next(gen)
    try:
        yield handle
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
