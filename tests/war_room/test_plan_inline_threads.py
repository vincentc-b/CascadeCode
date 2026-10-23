"""Inline review-thread DOM regression (feat_019_001 / task_019_001_002)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent
_INLINE_CASES = _DIR / "plan_inline_threads_cases.mjs"
_PLAN_JS = _DIR.parents[1] / "cascade" / "war_room" / "static" / "plan_viewer.js"
_PLAN_CSS = _DIR.parents[1] / "cascade" / "war_room" / "static" / "plan_viewer.css"


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


def test_plan_inline_threads_mjs_cases() -> None:
    _run_node_cases(_INLINE_CASES)


def test_plan_viewer_exports_inline_test_hooks() -> None:
    plan_js = _PLAN_JS.read_text(encoding="utf-8")
    assert "initPlanComments: initPlanComments" in plan_js
    assert "options.testHooks" in plan_js
    assert "renderComments: renderCommentThreads" in plan_js


def test_plan_viewer_inline_layout_css_guards_narrow_widths() -> None:
    css = _PLAN_CSS.read_text(encoding="utf-8")
    assert ".plan-inline-threads" in css
    assert "max-width: 100%" in css
    assert "overflow-wrap: anywhere" in css
    assert "@media (max-width: 36rem)" in css
