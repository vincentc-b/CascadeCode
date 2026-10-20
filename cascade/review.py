"""Feature draft-MR lifecycle and review-comment delivery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.errors import GitError, NotFound
from cascade.board.store import read_doc
from cascade.tracking import (
    MergeRequest,
    create_merge_request,
    forge_ready,
    merge_request_snapshot,
    push_branch,
    reply_to_merge_request,
)
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import get_integration_worktree, integration_branch, locate_trunk


def _state_path(root: Path) -> Path:
    return Path(root) / ".cascade" / "reviews.json"


def _load(root: Path) -> dict[str, dict[str, object]]:
    path = _state_path(root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save(root: Path, state: dict[str, dict[str, object]]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def review_enabled(root: Path) -> bool:
    return forge_ready(locate_trunk(root))


def ensure_feature_review(feature_id: str, *, root: Path) -> MergeRequest | None:
    """Push a completed feature line and open one draft MR to its epic line."""

    trunk = locate_trunk(root)
    if not review_enabled(trunk):
        return None
    state = _load(trunk)
    existing = state.get(feature_id)
    if existing:
        return _record_to_mr(existing)
    doc = read_doc(feature_id, root=trunk)
    if doc.meta.tier != "feature" or not doc.meta.parent:
        raise NotFound(feature_id)
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is None:
        raise GitError(f"feature worktree missing: {feature_id}")
    source = integration_branch("feature", feature_id)
    target = integration_branch("epic", doc.meta.parent)
    # The target must exist remotely for a stacked feature MR.
    epic_entry = get_integration_worktree(trunk, "epic", doc.meta.parent)
    if epic_entry is None:
        raise GitError(f"epic worktree missing: {doc.meta.parent}")
    push_branch(epic_entry.path, target)
    push_branch(entry.path, source)
    mr = create_merge_request(
        entry.path,
        title=f"{feature_id}: {doc.meta.title}",
        body=(
            f"Implements `{feature_id}` for `{doc.meta.parent}`. This draft is managed by "
            "Cascade; review comments are delivered to the Feature Team."
        ),
        source_branch=source,
        target_branch=target,
        draft=True,
    )
    state[feature_id] = {
        "url": mr.url,
        "number": mr.number,
        "forge": mr.forge,
        "source_branch": source,
        "target_branch": target,
        "draft": True,
        "seen_comments": [],
    }
    _save(trunk, state)
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "feature_review_opened",
                "id": feature_id,
                "url": mr.url,
                "message": f"Draft review opened for {feature_id}",
            },
            dest="war_room",
        ),
        root=trunk,
    )
    return mr


def poll_feature_reviews(root: Path) -> None:
    trunk = locate_trunk(root)
    state = _load(trunk)
    changed = False
    for feature_id, record in list(state.items()):
        if record.get("closed"):
            continue
        try:
            mr = _record_to_mr(record)
            entry = get_integration_worktree(trunk, "feature", feature_id)
            if entry is not None:
                push_branch(entry.path, mr.source_branch)
            snapshot = merge_request_snapshot(trunk, mr)
        except (GitError, ValueError):
            continue
        seen = {str(item) for item in record.get("seen_comments", [])}
        for row in snapshot.get("comments", []):
            if not isinstance(row, dict):
                continue
            comment_id = str(row.get("id") or row.get("databaseId") or row.get("created_at") or "")
            body = str(row.get("body") or row.get("note") or "").strip()
            author_raw = row.get("author") or row.get("user") or {}
            author = str(author_raw.get("login") or author_raw.get("username") or "reviewer") if isinstance(author_raw, dict) else str(author_raw)
            if not comment_id or comment_id in seen or not body:
                continue
            seen.add(comment_id)
            if "<!-- cascade-agent-reply -->" in body:
                continue
            append_event(
                feature_id,
                Event(
                    type="MergeRequestComment",
                    ts=datetime.now(timezone.utc),
                    payload={
                        "feature_id": feature_id,
                        "comment_id": comment_id,
                        "author": author,
                        "body": body,
                        "merge_request_url": mr.url,
                        "instruction": "Assess holistically, mint fixer tasks when code changes are needed, and reply through reply_merge_request_comment.",
                    },
                    dest=feature_id,
                ),
                root=trunk,
            )
        record["seen_comments"] = sorted(seen)
        if snapshot.get("state") == "merged":
            from cascade.boss.rollup import try_complete_feature

            if try_complete_feature(feature_id, root=trunk, review_merged=True):
                record["closed"] = True
        changed = True
    if changed:
        _save(trunk, state)


def reply_feature_review(feature_id: str, body: str, *, root: Path) -> str:
    state = _load(locate_trunk(root))
    record = state.get(feature_id)
    if record is None:
        raise NotFound(f"no merge request for {feature_id}")
    mr = _record_to_mr(record)
    reply_to_merge_request(
        locate_trunk(root),
        mr.url,
        body.rstrip() + "\n\n<!-- cascade-agent-reply -->",
    )
    return mr.url


def _record_to_mr(record: dict[str, object]) -> MergeRequest:
    return MergeRequest(
        url=str(record["url"]),
        number=str(record["number"]) if record.get("number") is not None else None,
        forge=str(record["forge"]),  # type: ignore[arg-type]
        source_branch=str(record["source_branch"]),
        target_branch=str(record["target_branch"]),
        draft=bool(record.get("draft", True)),
    )
