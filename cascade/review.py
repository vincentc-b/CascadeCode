"""Feature draft-MR lifecycle and review-comment delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.errors import GitError, NotFound
from cascade.board.store import read_doc
from cascade.tracking import (
    MergeRequest,
    create_merge_request,
    fast_forward_branch,
    forge_ready,
    merge_request_snapshot,
    push_branch,
    reply_to_merge_request,
)
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_branch,
    load_registry,
    locate_trunk,
    merged_board,
)


@dataclass(frozen=True)
class OpenReviewContext:
    feature_id: str
    epic_id: str | None
    feature_title: str | None
    epic_title: str | None


@dataclass(frozen=True)
class OpenReview:
    """Read-model row for one open entry in the durable review registry."""

    id: str
    url: str
    state: str
    context: OpenReviewContext


def list_open_reviews(*, root: Path) -> list[OpenReview]:
    """Return open registry rows without mutating durable review state."""

    trunk = locate_trunk(root)
    state = _load(trunk)
    board = merged_board(trunk)
    rows: list[OpenReview] = []
    for feature_id in sorted(state):
        record = state[feature_id]
        if not isinstance(record, dict) or record.get("closed"):
            continue
        url = str(record.get("url") or "").strip()
        if not url:
            continue
        epic_id = _review_target_epic(record)
        feature_meta = board.by_id.get(feature_id)
        epic_meta = board.by_id.get(epic_id) if epic_id else None
        rows.append(
            OpenReview(
                id=feature_id,
                url=url,
                state="awaiting_review",
                context=OpenReviewContext(
                    feature_id=feature_id,
                    epic_id=epic_id,
                    feature_title=feature_meta.title if feature_meta else None,
                    epic_title=epic_meta.title if epic_meta else None,
                ),
            )
        )
    return rows


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


def feature_review_pending(feature_id: str, *, root: Path) -> bool:
    """True while a completed source branch still awaits its forge merge."""

    trunk = locate_trunk(root)
    record = _load(trunk).get(feature_id)
    if record is not None:
        return not bool(record.get("closed"))
    # Closing the plan precedes publication. Treat that preparation window as
    # pending too, so a sibling cannot dispatch if normalization or MR creation
    # fails before reviews.json is written.
    if not review_enabled(trunk):
        return False
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is None or not entry.path.is_dir():
        return False
    try:
        doc = read_doc(feature_id, root=entry.path)
    except NotFound:
        return False
    return doc.meta.status == "completed" and doc.meta.path.parent.name == "3_completed"


def feature_review_view(feature_id: str, *, root: Path) -> dict[str, object] | None:
    """Return operator-facing review state without polling the forge."""

    trunk = locate_trunk(root)
    record = _load(trunk).get(feature_id)
    if record is not None:
        return {
            "state": "merged" if record.get("closed") else "awaiting_review",
            "url": str(record.get("url") or ""),
            "number": record.get("number"),
            "draft": bool(record.get("draft", False)),
        }
    if feature_review_pending(feature_id, root=trunk):
        return {
            "state": "preparing_review",
            "url": "",
            "number": None,
            "draft": False,
        }
    return None


def feature_review_views(
    feature_ids: list[str] | tuple[str, ...] | set[str],
    *,
    root: Path,
) -> dict[str, dict[str, object] | None]:
    """Build multiple operator review views with one registry/sidecar load."""

    trunk = locate_trunk(root)
    state = _load(trunk)
    ids = list(feature_ids)
    missing = [feature_id for feature_id in ids if feature_id not in state]
    enabled = bool(missing) and review_enabled(trunk)
    entries = {
        entry.work_id: entry
        for entry in load_registry(trunk)
        if enabled and entry.kind == "feature" and entry.work_id in missing
    }
    views: dict[str, dict[str, object] | None] = {}
    for feature_id in ids:
        record = state.get(feature_id)
        if record is not None:
            views[feature_id] = {
                "state": "merged" if record.get("closed") else "awaiting_review",
                "url": str(record.get("url") or ""),
                "number": record.get("number"),
                "draft": bool(record.get("draft", False)),
            }
            continue
        entry = entries.get(feature_id)
        pending = False
        if entry is not None and entry.path.is_dir():
            try:
                doc = read_doc(feature_id, root=entry.path)
            except NotFound:
                pass
            else:
                pending = (
                    doc.meta.status == "completed"
                    and doc.meta.path.parent.name == "3_completed"
                )
        views[feature_id] = (
            {
                "state": "preparing_review",
                "url": "",
                "number": None,
                "draft": False,
            }
            if pending
            else None
        )
    return views


def epic_has_pending_feature_review(epic_id: str, *, root: Path) -> bool:
    """True when any child feature is prepared for or awaiting forge review."""

    trunk = locate_trunk(root)
    from cascade.workspace.integration_worktree import merged_board

    for meta in merged_board(trunk).by_id.values():
        if meta.tier != "feature" or meta.parent != epic_id:
            continue
        if feature_review_pending(meta.id, root=trunk):
            return True
    return False


def ensure_feature_review(feature_id: str, *, root: Path) -> MergeRequest | None:
    """Push a completed feature line and open one MR to its epic line."""

    trunk = locate_trunk(root)
    if not review_enabled(trunk):
        return None
    state = _load(trunk)
    existing = state.get(feature_id)
    if existing:
        mr = _record_to_mr(existing)
        _ensure_opened_toast(feature_id, mr, existing, state=state, root=trunk)
        return mr
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is None:
        raise GitError(f"feature worktree missing: {feature_id}")
    doc = read_doc(feature_id, root=entry.path)
    if doc.meta.tier != "feature" or not doc.meta.parent:
        raise NotFound(feature_id)
    if doc.meta.status != "completed" or doc.meta.path.parent.name != "3_completed":
        raise GitError(f"{feature_id} must be completed on its source branch before review")
    source = integration_branch("feature", feature_id)
    target = integration_branch("epic", doc.meta.parent)
    # The target must exist remotely for a stacked feature MR.
    epic_entry = get_integration_worktree(trunk, "epic", doc.meta.parent)
    if epic_entry is None:
        raise GitError(f"epic worktree missing: {doc.meta.parent}")
    from cascade.feature.publication import prepare_feature_publication

    publication = prepare_feature_publication(feature_id, root=trunk)
    push_branch(epic_entry.path, target)
    remote_lease_sha = getattr(publication, "remote_lease_sha", None)
    if remote_lease_sha is not None:
        push_branch(entry.path, source, force_with_lease=remote_lease_sha)
    else:
        push_branch(entry.path, source)
    mr = create_merge_request(
        entry.path,
        title=f"{feature_id}: {doc.meta.title}",
        body=(
            f"Implements `{feature_id}` for `{doc.meta.parent}`. This review is managed by "
            "Cascade; review comments are delivered to the Feature Team."
        ),
        source_branch=source,
        target_branch=target,
        draft=False,
    )
    state[feature_id] = {
        "url": mr.url,
        "number": mr.number,
        "forge": mr.forge,
        "source_branch": source,
        "target_branch": target,
        "draft": False,
        "seen_comments": [],
        "toast_notified": False,
    }
    _save(trunk, state)
    _ensure_opened_toast(feature_id, mr, state[feature_id], state=state, root=trunk)
    return mr


def _ensure_opened_toast(
    feature_id: str,
    mr: MergeRequest,
    record: dict[str, object],
    *,
    state: dict[str, dict[str, object]],
    root: Path,
) -> None:
    """Deliver the linked review notification at least once across restarts."""

    if record.get("toast_notified") is True:
        return
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "feature_review_opened",
                "id": feature_id,
                "url": mr.url,
                "message": f"Review opened for {feature_id}",
            },
            dest="war_room",
        ),
        root=root,
    )
    record["toast_notified"] = True
    state[feature_id] = record
    _save(root, state)


def reconcile_feature_review_completions(root: Path) -> list[str]:
    """Finalize merged feature reviews from durable registry state; idempotent."""

    trunk = locate_trunk(root)
    state = _load(trunk)
    finalized: list[str] = []
    changed = False
    from cascade.boss.rollup import feature_completed_recorded, try_complete_feature

    for feature_id, record in list(state.items()):
        if record.get("closed"):
            epic_id = _review_target_epic(record)
            if epic_id and not feature_completed_recorded(feature_id, epic_id, root=trunk):
                if try_complete_feature(feature_id, root=trunk, review_merged=True):
                    finalized.append(feature_id)
            continue
        try:
            mr = _record_to_mr(record)
            snapshot = merge_request_snapshot(trunk, mr)
        except (GitError, ValueError, KeyError):
            continue
        if snapshot.get("state") != "merged":
            continue
        epic_id = _review_target_epic(record)
        before = (
            feature_completed_recorded(feature_id, epic_id, root=trunk)
            if epic_id
            else True
        )
        if _finalize_merged_review_record(feature_id, record, mr, trunk=trunk):
            record["closed"] = True
            changed = True
            if epic_id and not before and feature_completed_recorded(
                feature_id, epic_id, root=trunk
            ):
                finalized.append(feature_id)
    if changed:
        _save(trunk, state)
    return finalized


def _review_target_epic(record: dict[str, object]) -> str | None:
    target = str(record.get("target_branch") or "")
    prefix = "epic/"
    if target.startswith(prefix):
        return target.removeprefix(prefix)
    return None


def _finalize_merged_review_record(
    feature_id: str,
    record: dict[str, object],
    mr: MergeRequest,
    *,
    trunk: Path,
) -> bool:
    from cascade.boss.rollup import try_complete_feature

    try:
        _sync_merged_target(trunk, mr)
        return try_complete_feature(feature_id, root=trunk, review_merged=True)
    except GitError:
        return False


def poll_feature_reviews(root: Path) -> None:
    trunk = locate_trunk(root)
    state = _load(trunk)
    changed = False
    for feature_id, record in list(state.items()):
        if record.get("closed"):
            continue
        try:
            mr = _record_to_mr(record)
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
            if _finalize_merged_review_record(feature_id, record, mr, trunk=trunk):
                record["closed"] = True
            else:
                # Do not acknowledge completion until the local epic worktree
                # contains the exact tree accepted by the forge.
                continue
        else:
            entry = get_integration_worktree(trunk, "feature", feature_id)
            if entry is not None:
                try:
                    from cascade.feature.publication import prepare_feature_publication

                    publication = prepare_feature_publication(feature_id, root=trunk)
                    remote_lease_sha = getattr(publication, "remote_lease_sha", None)
                    if remote_lease_sha is not None:
                        push_branch(
                            entry.path,
                            mr.source_branch,
                            force_with_lease=remote_lease_sha,
                        )
                    else:
                        push_branch(entry.path, mr.source_branch)
                except GitError:
                    # Fail closed: never publish checkpoint/merge noise after the
                    # initial review was opened.
                    continue
        changed = True
    if changed:
        _save(trunk, state)


def _sync_merged_target(trunk: Path, mr: MergeRequest) -> str:
    prefix = "epic/"
    if not mr.target_branch.startswith(prefix):
        raise GitError(f"unexpected feature review target: {mr.target_branch}")
    epic_id = mr.target_branch.removeprefix(prefix)
    entry = get_integration_worktree(trunk, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing: {epic_id}")
    return fast_forward_branch(entry.path, mr.target_branch)


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
