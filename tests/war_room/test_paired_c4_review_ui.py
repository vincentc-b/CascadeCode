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

