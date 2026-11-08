from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_audit_status_ui_matches_durable_payload() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the War Room JavaScript harness")
    case = Path(__file__).with_name("audit_status_ui_cases.mjs")
    subprocess.run([node, str(case)], check=True)
