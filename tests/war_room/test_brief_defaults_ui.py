"""Brief default selector helpers (task_006_002_002) — Node cases."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent
_CASES = _DIR / "brief_defaults_ui_cases.mjs"


def _find_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    for candidate in ("/usr/bin/node", "/usr/local/bin/node"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _run_node_cases(path: Path) -> None:
    node = _find_node()
    if not node:
        pytest.skip("node not on PATH")
    result = subprocess.run(
        [node, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def test_brief_defaults_ui_cases() -> None:
    _run_node_cases(_CASES)


def test_brief_dialog_uses_inventory_backed_module() -> None:
    static = Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static"
    war_room_source = (static / "war_room.js").read_text(encoding="utf-8")
    assert "BriefDefaultsUi" in war_room_source
    assert "/api/brief/inventory" in war_room_source
    assert "buildSubmitPayload" in war_room_source
    assert 'name="manager_model"' not in war_room_source
