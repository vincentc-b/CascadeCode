"""Existing forge reviews are reused when an epic close is retried."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import cascade.tracking as tracking


def test_find_merge_request_reuses_matching_open_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tracking, "detect_forge", lambda _root: "github")
    rows = [
        {"url": "https://github.example/pull/1", "number": 1, "baseRefName": "other", "isDraft": False, "state": "OPEN"},
        {"url": "https://github.example/pull/2", "number": 2, "baseRefName": "main", "isDraft": False, "state": "CLOSED"},
        {"url": "https://github.example/pull/3", "number": 3, "baseRefName": "main", "isDraft": True, "state": "OPEN"},
    ]

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        assert root == tmp_path
        assert args[:6] == ["gh", "pr", "list", "--state", "all", "--head"]
        return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")

    mr = tracking.find_merge_request(
        tmp_path, source_branch="epic/epic_001", target_branch="main", runner=runner
    )
    assert mr is not None
    assert mr.url == "https://github.example/pull/3"
    assert mr.number == "3"
    assert mr.draft is True
