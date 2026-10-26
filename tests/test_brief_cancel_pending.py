"""Pending backlog cancellations survive reloads and cannot open a second review."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import cascade.brief_cancel_pr as cancel
import cascade.war_room.brief_edit_routes as routes
from cascade.brief_edit_pr import BriefEditError
from cascade.tracking import MergeRequest
from tests.support import add_doc, make_repo


def _review(number: int, *, state: str = "OPEN") -> dict[str, object]:
    return {
        "url": f"https://github.com/example/repo/pull/{number}",
        "number": number,
        "headRefName": f"cascade/brief-cancel/epic_025-{number:08x}",
        "baseRefName": "main",
        "isDraft": False,
        "createdAt": f"2026-10-25T{number % 24:02d}:00:00Z",
        "state": state,
    }


def test_open_cancellation_lookup_chooses_first_review_and_ignores_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cancel, "detect_forge", lambda _repo, remote="origin": "github")
    monkeypatch.setattr(cancel, "resolve_product_trunk", lambda _repo: "main")
    rows = [_review(85), _review(84), _review(83, state="CLOSED")]

    def runner(args: list[str], _repo: Path) -> subprocess.CompletedProcess[str]:
        assert args[:5] == ["gh", "pr", "list", "--state", "open"]
        return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")

    monkeypatch.setattr(cancel, "_forge", runner)
    found = cancel.open_brief_cancellations(tmp_path)
    assert found["epic_025"].url.endswith("/84")

    rows[:] = [_review(85, state="CLOSED"), _review(84, state="CLOSED")]
    assert cancel.open_brief_cancellations(tmp_path) == {}


def test_pending_cancellation_rejects_repeat_before_pushing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, git=True)
    doc = add_doc(repo, id="epic_025", title="Flex mode revival", tier="epic")
    review = MergeRequest(
        url="https://github.com/example/repo/pull/84", number="84", forge="github",
        source_branch="cascade/brief-cancel/epic_025-a94ee58a", target_branch="main", draft=False,
    )
    monkeypatch.setattr(cancel, "resolve_product_trunk", lambda _repo: "main")
    monkeypatch.setattr(cancel, "_fetch_remote_trunk", lambda *_args, **_kwargs: "base")
    monkeypatch.setattr(
        cancel, "_fetched_brief",
        lambda *_args: (doc, "docs/epics/1_backlog/epic_025_flex_mode_revival.md", "rev"),
    )
    monkeypatch.setattr(cancel, "forge_ready", lambda _repo: True)
    monkeypatch.setattr(cancel, "open_brief_cancellations", lambda _repo: {"epic_025": review})
    monkeypatch.setattr(cancel, "push_branch", lambda *_args, **_kwargs: pytest.fail("opened another branch"))

    with pytest.raises(BriefEditError) as exc_info:
        cancel.submit_brief_cancel(
            repo,
            {
                "epic_id": "epic_025",
                "reason": "duplicate",
                "source_path": "docs/epics/1_backlog/epic_025_flex_mode_revival.md",
                "source_revision": "rev",
            },
        )
    assert exc_info.value.code == "pending_cancel"
    assert exc_info.value.review_url == review.url


def test_cancellation_api_exposes_existing_link_and_duplicate_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = MergeRequest(
        url="https://github.com/example/repo/pull/84", number="84", forge="github",
        source_branch="cascade/brief-cancel/epic_025-a94ee58a", target_branch="main", draft=False,
    )

    class Handler:
        server = type("Server", (), {"root": tmp_path})()

        def __init__(self) -> None:
            self.status = 0
            self.body: dict[str, object] = {}

        def _json_response(self, status: int, body: dict[str, object]) -> None:
            self.status, self.body = status, body

    monkeypatch.setattr(routes, "open_brief_cancellations", lambda _root: {"epic_025": review})
    handler = Handler()
    routes.handle_get_brief_cancellations(handler)  # type: ignore[arg-type]
    assert handler.status == 200
    assert handler.body["reviews"] == {"epic_025": {"url": review.url, "number": "84"}}

    def repeat(_root: Path, _body: dict[str, object]) -> MergeRequest:
        raise BriefEditError("already pending", code="pending_cancel", review_url=review.url)

    monkeypatch.setattr(routes, "submit_brief_cancel", repeat)
    routes.handle_post_brief_cancel(handler, {"epic_id": "epic_025"})  # type: ignore[arg-type]
    assert handler.status == 409
    assert handler.body["code"] == "pending_cancel"
    assert handler.body["review_url"] == review.url
