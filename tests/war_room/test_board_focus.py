"""Board focus pure helpers (task_053–055) — Node cases."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent
_COLLAPSE_CASES = _DIR / "board_focus_collapse_cases.mjs"
_EPIC_LENS_CASES = _DIR / "board_focus_epic_lens_cases.mjs"
_FEATURE_LENS_CASES = _DIR / "board_focus_feature_lens_cases.mjs"


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


def test_board_focus_collapse_cases() -> None:
    _run_node_cases(_COLLAPSE_CASES)


def test_board_focus_epic_lens_cases() -> None:
    _run_node_cases(_EPIC_LENS_CASES)


def test_board_focus_feature_lens_cases() -> None:
    _run_node_cases(_FEATURE_LENS_CASES)


def test_attach_applies_feature_selection_without_detach_on_lens_change() -> None:
    """Feature attach uses shared selection helper; card clicks do not detach."""
    js_path = _DIR.parents[1] / "cascade" / "war_room" / "static" / "war_room.js"
    source = js_path.read_text(encoding="utf-8")
    assert "applyFeatureSelection" in source
    attach_block = source.split("async function attach", 1)[1].split("async function detach", 1)[0]
    assert "applyFeatureSelection" in attach_block
    feature_click = source.split('if (tier === "features")', 1)[1].split("row.appendChild(actions)", 1)[0]
    assert "detach" not in feature_click
    epic_click = source.split('if (tier === "epics")', 1)[1].split("if (tier === \"features\")", 1)[0]
    assert "detach" not in epic_click
