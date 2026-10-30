"""Feature draft-MR lifecycle and review-comment delivery."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.errors import BoardError, GitError, NotFound
from cascade.board.store import move_doc, read_doc, read_doc_in_worktree
from cascade.tracking import (
    MergeRequest,
    create_merge_request,
    find_merge_request,
    fast_forward_branch,
    forge_ready,
    merge_request_snapshot,
    push_branch,
    reply_to_merge_request,
)
from cascade.watchdog.events import append_event
from cascade.watchdog.lock import process_lock
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


def review_record_for_feature(feature_id: str, *, root: Path) -> dict[str, object] | None:
    trunk = locate_trunk(root)
    record = _load(trunk).get(feature_id)
    return dict(record) if isinstance(record, dict) else None


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
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".reviews.", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


@contextmanager
def _registry_write_lock(root: Path):
    """Serialize short read-modify-write steps across worker and CLI processes."""

    lock_path = _state_path(root).with_suffix(".lock")
    with process_lock:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _update_record(
    root: Path,
    feature_id: str,
    changes: dict[str, object],
    *,
    create: bool = False,
    only_if_absent: bool = False,
) -> dict[str, object] | None:
    """Merge one feature's fields into the latest registry without losing peers."""

    with _registry_write_lock(root):
        state = _load(root)
        existing = state.get(feature_id)
        if not isinstance(existing, dict):
            if not create:
                return None
            existing = {}
        elif only_if_absent and existing:
            return dict(existing)
        updated = dict(existing)
        updated.update(changes)
        if "seen_comments" in changes:
            previous_seen = existing.get("seen_comments")
            previous_seen = previous_seen if isinstance(previous_seen, list) else []
            incoming_seen = changes["seen_comments"]
            incoming_seen = incoming_seen if isinstance(incoming_seen, list) else []
            updated["seen_comments"] = sorted(
                {str(row) for row in previous_seen}
                | {str(row) for row in incoming_seen}
            )
        if updated != existing:
            state[feature_id] = updated
            _save(root, state)
        return updated


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


def ensure_epic_review(epic_id: str, *, root: Path) -> MergeRequest | None:
    """Publish a completed epic line to the product trunk for human review."""

    trunk = locate_trunk(root)
    if not review_enabled(trunk):
        return None
    from cascade.workspace.trunk import resolve_product_trunk

    entry = get_integration_worktree(trunk, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing: {epic_id}")
    doc = read_doc(epic_id, root=entry.path)
    if doc.meta.tier != "epic":
        raise NotFound(epic_id)
    source = integration_branch("epic", epic_id)
    target = resolve_product_trunk(trunk)
    _restore_unrelated_specs_for_epic_review(entry.path, trunk, epic_id)
    push_branch(entry.path, source)
    existing = find_merge_request(
        entry.path, source_branch=source, target_branch=target
    )
    if existing is not None:
        return existing
    return create_merge_request(
        entry.path,
        title=f"{epic_id}: {doc.meta.title}",
        body=f"Delivers `{epic_id}` to `{target}`. Review the completed epic before merging.",
        source_branch=source,
        target_branch=target,
        draft=False,
    )


def _restore_unrelated_specs_for_epic_review(
    epic_root: Path, trunk: Path, epic_id: str
) -> None:
    """Keep activation's spec scrub from deleting remote trunk's other specs."""

    from cascade.workspace.closeout import create_verified_trunk_workspace

    def git(args: list[str], cwd: Path) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            raise GitError((result.stderr or result.stdout).strip() or "git failed")
        return result.stdout.strip()

    if git(["status", "--porcelain", "--untracked-files=no"], epic_root):
        raise GitError(f"epic worktree has uncommitted changes: {epic_id}")
    with create_verified_trunk_workspace(trunk) as workspace:
        changed = git(
            ["diff", "--name-only", workspace.revision, "HEAD", "--", "docs/features", "docs/tasks"],
            epic_root,
        ).splitlines()
        number = epic_id.removeprefix("epic_")
        restore = [
            path for path in changed
            if not Path(path).name.startswith((f"feat_{number}_", f"task_{number}_"))
            and (workspace.path / path).is_file()
        ]
        if not restore:
            return
        git(["restore", f"--source={workspace.revision}", "--staged", "--worktree", "--", *restore], epic_root)
        git(["-c", "commit.gpgsign=false", "commit", "-m", f"docs: preserve unrelated specs for {epic_id} review", "--", *restore], epic_root)


def ensure_feature_review(feature_id: str, *, root: Path) -> MergeRequest | None:
    """Push a completed feature line and open one MR to its epic line."""

    trunk = locate_trunk(root)
    if not review_enabled(trunk):
        return None
    state = _load(trunk)
    existing = state.get(feature_id)
    if existing:
        mr = _record_to_mr(existing)
        _ensure_opened_toast(feature_id, mr, existing, root=trunk)
        return mr
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is None:
        raise GitError(f"feature worktree missing: {feature_id}")
    doc = read_doc(feature_id, root=entry.path)
    if doc.meta.tier != "feature" or not doc.meta.parent:
        raise NotFound(feature_id)
    ready_for_review = doc.meta.status == "completed" and doc.meta.path.parent.name == "3_completed"
    if not ready_for_review:
        if doc.meta.status != "active" or doc.meta.path.parent.name != "2_active":
            raise GitError(f"{feature_id} must be completed on its source branch before review")
        from cascade.boss.rollup import _rollup_gates_pass

        if not _rollup_gates_pass(
            feature_id, doc.body, merged_board(trunk), trunk
        ):
            raise GitError(f"{feature_id} is not ready for review publication")
    source = integration_branch("feature", feature_id)
    from cascade.stacked_dispatch import review_target_branch

    target = review_target_branch(feature_id, doc.meta.parent, root=trunk)
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
    record = _update_record(trunk, feature_id, {
        "url": mr.url,
        "number": mr.number,
        "forge": mr.forge,
        "source_branch": source,
        "target_branch": target,
        "draft": False,
        "seen_comments": [],
        "toast_notified": False,
    }, create=True, only_if_absent=True)
    assert record is not None
    recorded_mr = _record_to_mr(record)
    _ensure_opened_toast(feature_id, recorded_mr, record, root=trunk)
    return mr if recorded_mr.url == mr.url else recorded_mr


def _ensure_opened_toast(
    feature_id: str,
    mr: MergeRequest,
    record: dict[str, object],
    *,
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
    _update_record(root, feature_id, {"toast_notified": True})


def reconcile_feature_review_completions(root: Path) -> list[str]:
    """Finalize merged feature reviews from durable registry state; idempotent."""

    trunk = locate_trunk(root)
    state = _load(trunk)
    finalized: list[str] = []
    from cascade.boss.rollup import feature_completed_recorded, try_complete_feature

    board = merged_board(trunk) if any(record.get("closed") for record in state.values()) else None

    for feature_id, record in list(state.items()):
        if record.get("closed"):
            epic_id = _review_target_epic(record)
            if board is not None and _closed_review_has_active_target(
                feature_id, record, board=board, trunk=trunk
            ):
                # Older supervisors could record closure before completing the
                # accepted feature copy on its epic branch. Repair that state
                # even when the completion event was already emitted.
                try:
                    mr = _record_to_mr(record)
                except (GitError, ValueError, KeyError):
                    continue
                before = bool(
                    epic_id and feature_completed_recorded(feature_id, epic_id, root=trunk)
                )
                if _finalize_merged_review_record(feature_id, record, mr, trunk=trunk):
                    if epic_id and not before and feature_completed_recorded(
                        feature_id, epic_id, root=trunk
                    ):
                        finalized.append(feature_id)
                continue
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
            _update_record(trunk, feature_id, {"closed": True})
            if epic_id and not before and feature_completed_recorded(
                feature_id, epic_id, root=trunk
            ):
                finalized.append(feature_id)
    return finalized


def _closed_review_has_active_target(
    feature_id: str, record: dict[str, object], *, board, trunk: Path
) -> bool:
    epic_id = _review_target_epic(record)
    entry = get_integration_worktree(trunk, "epic", epic_id) if epic_id else None
    meta = board.by_id.get(feature_id)
    return bool(
        entry is not None
        and meta is not None
        and meta.tier == "feature"
        and meta.status == "active"
        and meta.path.parent.name == "2_active"
        and meta.path.is_relative_to(entry.path)
    )


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
        epic_root = _close_merged_feature_on_target(feature_id, record, trunk=trunk)
        # The accepted source tree may still have an active feature document.
        # Publish its terminal lifecycle commit before acknowledging closure.
        push_branch(epic_root, mr.target_branch)
        return try_complete_feature(feature_id, root=trunk, review_merged=True)
    except (BoardError, OSError):
        return False


def _close_merged_feature_on_target(
    feature_id: str, record: dict[str, object], *, trunk: Path
) -> Path:
    """Persist completion on the epic line after its accepted review merge.

    The source feature doc is moved locally after initial MR publication. That
    local lifecycle commit is not part of the forge merge, so the accepted epic
    tree can still contain the active copy. Complete that copy before recording
    the review as closed or releasing dependent Features.
    """

    epic_id = _review_target_epic(record)
    entry = get_integration_worktree(trunk, "epic", epic_id) if epic_id else None
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing for merged feature {feature_id}")
    doc = read_doc_in_worktree(feature_id, entry.path)
    if doc.meta.tier != "feature" or doc.meta.parent != epic_id:
        raise GitError(f"merged feature target mismatch: {feature_id}")
    if doc.meta.status == "completed" and doc.meta.path.parent.name == "3_completed":
        return entry.path
    if doc.meta.status != "active" or doc.meta.path.parent.name != "2_active":
        raise GitError(f"merged feature is not active on epic branch: {feature_id}")
    move_doc(feature_id, "completed", root=entry.path)
    return entry.path


def poll_feature_reviews(root: Path) -> None:
    trunk = locate_trunk(root)
    state = _load(trunk)
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
        # Persist deliveries before any later publication/finalization failure.
        # Merge with the latest record so parallel reviews cannot be reopened.
        _update_record(trunk, feature_id, {"seen_comments": sorted(seen)})
        if snapshot.get("state") == "merged":
            if _finalize_merged_review_record(feature_id, record, mr, trunk=trunk):
                _update_record(trunk, feature_id, {"closed": True})
            else:
                # Do not acknowledge completion until the local epic worktree
                # contains the exact tree accepted by the forge.
                continue
        else:
            current = review_record_for_feature(feature_id, root=trunk)
            if current is None or current.get("closed"):
                continue
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


def live_merge_request_target_branch(record: dict[str, object], *, root: Path) -> str | None:
    """Read the forge-reported PR/MR base branch without mutating durable state."""

    url = str(record.get("url") or "").strip()
    if not url:
        return None
    trunk = locate_trunk(root)
    try:
        mr = _record_to_mr(record)
        snapshot = merge_request_snapshot(trunk, mr)
    except (GitError, ValueError, KeyError):
        return None
    live = str(snapshot.get("target_branch") or "").strip()
    return live or None


def persist_review_target_branch(
    feature_id: str, target_branch: str, *, root: Path
) -> None:
    """Mirror a verified forge base into the durable review registry."""

    trunk = locate_trunk(root)
    _update_record(trunk, feature_id, {"target_branch": target_branch})
