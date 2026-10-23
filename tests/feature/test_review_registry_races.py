"""Concurrent review polling must preserve durable lifecycle decisions."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import cascade.review as review
from tests.support import make_repo


def _record(feature_id: str) -> dict[str, object]:
    return {
        "url": f"https://github.example/org/repo/pull/{feature_id}",
        "number": "1",
        "forge": "github",
        "source_branch": f"feat/{feature_id}",
        "target_branch": "epic/epic_001",
        "draft": False,
        "seen_comments": [],
        "toast_notified": True,
    }


def test_stale_review_poll_preserves_parallel_close_retarget_and_new_review(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"feat_001": _record("feat_001")}), encoding="utf-8")
    monkeypatch.setattr(review, "locate_trunk", lambda value: Path(value))
    monkeypatch.setattr(review, "get_integration_worktree", lambda *_args: None)
    monkeypatch.setattr(review, "_finalize_merged_review_record", lambda *_args, **_kwargs: True)

    polling = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def snapshot(_root, _mr):
        if threading.current_thread().name == "stale-review-poll":
            polling.set()
            assert release.wait(5)
            return {"state": "open", "comments": [{"id": "comment-1", "body": "Please check this."}]}
        return {"state": "merged", "comments": []}

    monkeypatch.setattr(review, "merge_request_snapshot", snapshot)

    def poll() -> None:
        try:
            review.poll_feature_reviews(root)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=poll, name="stale-review-poll")
    thread.start()
    try:
        assert polling.wait(5)
        review.persist_review_target_branch("feat_001", "epic/epic_002", root=root)
        review.reconcile_feature_review_completions(root)
        current = json.loads(state_path.read_text(encoding="utf-8"))
        current["feat_002"] = _record("feat_002")
        state_path.write_text(json.dumps(current), encoding="utf-8")
    finally:
        release.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["feat_001"]["closed"] is True
    assert state["feat_001"]["target_branch"] == "epic/epic_002"
    assert state["feat_001"]["seen_comments"] == ["comment-1"]
    assert "feat_002" in state
