"""Browser-facing dependency review rendering coverage."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_dependency_review_ui_cases() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("dependency_review_ui_cases.mjs")
    result = subprocess.run(
        [node, str(cases)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
