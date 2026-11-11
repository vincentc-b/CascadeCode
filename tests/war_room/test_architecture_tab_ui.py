"""Architecture tab navigation and shared-viewer wiring."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_architecture_tab_navigation_cases() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("architecture_tab_cases.mjs"))],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_war_room_exposes_accessible_architecture_tab_and_shared_viewer() -> None:
    template = (ROOT / "cascade/war_room/templates/war_room.html").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "cascade/war_room/static/architecture_tab.js").read_text(
        encoding="utf-8"
    )

    assert 'id="war-room-architecture-tab"' in template
    assert 'role="tabpanel"' in template
    assert template.index("/static/plan_viewer.js") < template.index(
        "/static/architecture_tab.js"
    )
    assert "createSemanticC4Viewer" in script
    assert "cascade:architecture-context" in script
    assert "cascade:architecture-selection" in script
    assert "/status" in script
    assert "Refresh whole snapshot" in template
    assert "Requirements &amp; decisions" in template
    assert 'id="architecture-document-preview"' in template
    assert template.index("/static/vendor/marked.min.js") < template.index(
        "/static/plan_viewer.js"
    )
    assert "/context?" in script
    assert "Unmapped target" in script
    assert "Broader design index" in script
    assert "markdownToHtml" in script
