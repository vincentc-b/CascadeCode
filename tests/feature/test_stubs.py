"""Feature amendment tool registration (feat_006)."""

from __future__ import annotations

import importlib

import pytest

import cascade.feature.amendments as feature_amendments
import cascade.feature.stubs as feature_stubs
from cascade.feature.registry import clear_feature_tools, feature_tools
from cascade.feature.wiring import load_feature_tools


@pytest.fixture(autouse=True)
def _reload_tools() -> None:
    clear_feature_tools()
    load_feature_tools()
    yield
    clear_feature_tools()


def test_stubs_module_keeps_unavailable_type_for_legacy_imports() -> None:
    assert feature_stubs.FeatureToolUnavailable.status_code == 501


def test_propose_epic_amendment_registers_from_amendments_module() -> None:
    tools = feature_tools()
    assert tools["propose_epic_amendment"] is feature_amendments.propose_epic_amendment


def test_load_feature_tools_reregisters_propose_after_clear() -> None:
    clear_feature_tools()
    importlib.reload(feature_amendments)
    load_feature_tools()
    assert "propose_epic_amendment" in feature_tools()


def test_stubs_module_does_not_register_propose() -> None:
    clear_feature_tools()
    importlib.reload(feature_stubs)
    assert "propose_epic_amendment" not in feature_tools()
