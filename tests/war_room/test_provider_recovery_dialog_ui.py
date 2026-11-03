"""Inventory-backed provider recovery dialog browser contracts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_provider_recovery_dialog_ui_cases() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for browser-side UI contract tests")
    cases = Path(__file__).with_name("provider_recovery_dialog_ui_cases.mjs")
    subprocess.run([node, str(cases)], check=True)


def test_recovery_action_uses_modal_and_shared_inventory() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "cascade/war_room/static/war_room.js").read_text(encoding="utf-8")
    template = (root / "cascade/war_room/templates/war_room.html").read_text(encoding="utf-8")

    recovery_source = source[source.index("async function changeProviderRecovery") :]
    assert "globalThis.prompt" not in recovery_source
    assert 'id="provider-recovery-dialog"' in template
    assert "/static/provider_recovery_dialog_ui.js" in template
    assert '"/api/brief/inventory"' in source
    assert "ProviderRecoveryDialogUi.buildPayload" in source
