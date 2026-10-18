"""Plan viewer markdown render helpers — Node cases (task_057)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent
_PLAN_RENDER_CASES = _DIR / "test_plan_render.mjs"
_VENDOR = _DIR.parents[1] / "cascade" / "war_room" / "static" / "vendor"


def _find_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    for candidate in ("/usr/bin/node", "/usr/local/bin/node"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _node_supports_esm_cases(node: str) -> bool:
    probe = subprocess.run(
        [node, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        return False
    version = probe.stdout.strip().removeprefix("v")
    try:
        major = int(version.split(".", 1)[0])
    except ValueError:
        return False
    return major >= 16


def _run_node_cases(path: Path) -> None:
    node = _find_node()
    if not node:
        pytest.skip("node not on PATH")
    if not _node_supports_esm_cases(node):
        pytest.skip("node too old for node:assert/strict ESM cases")
    result = subprocess.run(
        [node, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def test_plan_render_mjs_cases() -> None:
    _run_node_cases(_PLAN_RENDER_CASES)


def test_vendor_markdown_and_mermaid_exist_on_disk() -> None:
    marked = _VENDOR / "marked.min.js"
    mermaid = _VENDOR / "mermaid.min.js"
    assert marked.is_file() and marked.stat().st_size > 1000
    assert mermaid.is_file() and mermaid.stat().st_size > 1000
    assert b"marked" in marked.read_bytes()[:200]
    assert b"mermaid" in mermaid.read_bytes()[:500].lower()
