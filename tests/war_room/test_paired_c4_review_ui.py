"""Browser-facing synchronized paired C4 review scenarios."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_paired_c4_review_cases() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("paired_c4_review_cases.mjs")
    result = subprocess.run(
        [node, str(cases)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_live_discussion_is_narrow_screen_safe() -> None:
    css = (
        Path(__file__).resolve().parents[2]
        / "cascade"
        / "war_room"
        / "static"
        / "plan_viewer.css"
    ).read_text(encoding="utf-8")
    assert ".paired-c4-thread-reply-form textarea" in css
    assert "min-width: 0" in css
    narrow = css.split("@media (max-width: 48rem)", 1)[1]
    assert ".paired-c4-thread-reply-form button" in narrow
    assert "width: 100%" in narrow

