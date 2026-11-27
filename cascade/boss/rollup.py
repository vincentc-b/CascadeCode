"""Feature closeout and completion rollup (task_041)."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import GitError, NotFound
from cascade.board.paths import column_for_status
from cascade.board.store import list_board, move_doc, read_doc, write_doc
from cascade.board.types import WorkId
from cascade.comments.store import read_comments
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.types import Event

_CLOSEOUT_HEADING = re.compile(r"^## Closeout\s*$", re.MULTILINE)
_NEXT_SECTION = re.compile(r"^## ", re.MULTILINE)
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentFeatureObligation:
    satisfied: bool
    generation: int = 0
    reason: str | None = None


def write_closeout(
    feature_id: WorkId, paragraph: str, *, root: Path | None = None
) -> str | None:
    """Ensure the feature doc has a ## Closeout section with ``paragraph``. Does not move columns."""

    repo = resolve_root(root)
    from cascade.workspace.doc_root import read_doc_resolved

    doc = read_doc_resolved(feature_id, root=repo)
    if doc.meta.tier != "feature":
        raise NotFound(feature_id)
    doc.body = _upsert_closeout_section(doc.body, paragraph)
    # ``read_doc`` may resolve the feature to its integration worktree even
    # when the caller is the product trunk. Commit from the checkout that owns
    # the absolute document path; adding a .cascade/worktrees path from trunk
    # is both the wrong branch and commonly rejected as ignored content.
    from cascade.workspace.integration_worktree import git_root_for_path

    try:
        owner_root = git_root_for_path(doc.meta.path)
    except GitError:
        owner_root = repo
    return write_doc(doc, root=owner_root)


def try_complete_feature(
    feature_id: WorkId,
    *,
    root: Path | None = None,
    review_merged: bool = False,
    review_generation: int | None = None,
) -> bool:
    """Complete the feature when all rollup gates pass; otherwise return False with no side effects."""

    repo = resolve_root(root)
    # Fresh forge/check evidence is collected outside the lifecycle critical
    # section. The Watchdog helper fences the exact receipt before mutation.
    from cascade.watchdog.incident_postcheck import reconcile_open_review_repair

    repair_postcheck = reconcile_open_review_repair(feature_id, root=repo)
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    with task_lifecycle_lock(root=repo):
        return _try_complete_feature(
            feature_id,
            root=repo,
            review_merged=review_merged,
            review_generation=review_generation,
            repair_postcheck=repair_postcheck,
        )


def _try_complete_feature(
    feature_id: WorkId,
    *,
    root: Path,
    review_merged: bool = False,
    review_generation: int | None = None,
    repair_postcheck: dict[str, object] | None = None,
) -> bool:
    """Locked Feature closeout implementation."""

    repo = resolve_root(root)
    from cascade.workspace.integration_worktree import locate_trunk, merged_board

    board = merged_board(locate_trunk(repo))
    if feature_id not in board.by_id:
        return False
    feature_meta = board.by_id[feature_id]
    if feature_meta.tier != "feature":
        return False
    if not _current_open_review_postcheck_matches(
        feature_id, repair_postcheck, root=repo
    ):
        return False
    from cascade.lifecycle_review_gate import require_lifecycle_review_gate
    from cascade.workspace.architecture_review import ArchitectureProposalError

    try:
        require_lifecycle_review_gate(feature_id, "closeout", root=repo)
    except ArchitectureProposalError:
        return False
    obligation = current_feature_obligation(
        feature_id,
        root=repo,
        board=board,
        review_generation=review_generation if review_merged else None,
    )
    if (
        feature_meta.status == "completed"
        and feature_meta.path.parent.name == "3_completed"
    ):
        if not obligation.satisfied:
            if not review_merged and obligation.reason == "review_not_published":
                from cascade.review import ensure_feature_review, review_enabled

                if review_enabled(repo):
                    ensure_feature_review(feature_id, root=repo)
            return False
        if review_merged and feature_meta.parent:
            _record_satisfied_repair(feature_id, obligation, repo)
            _emit_feature_completed(feature_id, feature_meta.parent, repo)
            _retire_feature_worktree(
                feature_id,
                feature_meta.parent,
                repo,
                merge_confirmed=True,
                current_obligation=obligation,
            )
        elif not review_merged:
            from cascade.review import (
                ensure_feature_review,
                feature_review_pending,
                review_enabled,
            )

            if review_enabled(repo) and feature_review_pending(feature_id, root=repo):
                ensure_feature_review(feature_id, root=repo)
                return False
            _retire_feature_worktree(
                feature_id,
                feature_meta.parent,
                repo,
                merge_confirmed=feature_completed_recorded(
                    feature_id, feature_meta.parent, root=repo
                ),
                current_obligation=obligation,
            )
        return True

    from cascade.workspace.doc_root import read_doc_resolved

    doc = read_doc_resolved(feature_id, root=repo)
    # A stale stacked review can be accepted after its predecessor has already
    # landed on the Epic branch.  Its recovery action is the durable proof
    # that the accepted change still needs an Epic-targeted reconciliation
    # review.  Only that review's merged callback may bypass this gate.
    if not review_merged:
        from cascade.stacked_review_recovery import stacked_review_completion_blocked

        if stacked_review_completion_blocked(feature_id, root=repo):
            return False

    # Closeout must not depend on another model turn after the last child lands.
    # A Feature Architect may replace this paragraph with a richer summary, but
    # the deterministic fallback records exactly which completed work unlocked
    # review and makes crash/restart recovery converge on the same state.
    if (
        not _closeout_present(doc.body)
        and _all_child_tasks_completed(feature_id, board)
        and not _has_open_human_comments(feature_id, repo)
    ):
        paragraph = _synthesized_closeout(feature_id, board)
        if paragraph is not None:
            write_closeout(feature_id, paragraph, root=repo)
            doc = read_doc_resolved(feature_id, root=repo)
    if not _rollup_gates_pass(feature_id, doc.body, board, repo):
        return False

    # A forge callback only selects the reconciliation path.  It is not proof
    # that the callback names the current generation or that the accepted merge
    # is reachable from the intended Epic target.
    if review_merged and not obligation.satisfied:
        return False

    if not review_merged:
        from cascade.review import ensure_feature_review, review_enabled
        from cascade.stacked_dispatch import feature_pull_request_linked

        if review_enabled(repo):
            mr = ensure_feature_review(feature_id, root=repo)
            if mr is None and not feature_pull_request_linked(feature_id, root=repo):
                return False
            owner_root = _feature_owner_root(feature_id, doc, repo)
            move_doc(feature_id, "completed", root=owner_root)
            return False

    if review_merged:
        # The forge merge already landed the source tree, including the completed
        # feature plan, on the epic branch. Polling records the terminal event but
        # must not create another source commit after review.
        if doc.meta.parent:
            _record_satisfied_repair(feature_id, obligation, repo)
            _emit_feature_completed(feature_id, doc.meta.parent, repo)
            _retire_feature_worktree(
                feature_id,
                doc.meta.parent,
                repo,
                merge_confirmed=True,
                current_obligation=obligation,
            )
            return True
        return False

    epic_id = doc.meta.parent
    if not epic_id:
        return False

    from cascade.boss.merge import merge_feature_branch

    from cascade.board.errors import GitError
    from cascade.workspace.integration_worktree import (
        get_integration_worktree,
        git_root_for_path,
        locate_trunk,
    )

    trunk = locate_trunk(repo)
    feat_entry = get_integration_worktree(trunk, "feature", feature_id)
    if feat_entry is not None and feat_entry.path.is_dir():
        owner_root = feat_entry.path
    else:
        try:
            owner_root = git_root_for_path(doc.meta.path)
        except GitError:
            owner_root = repo
    merge_result = merge_feature_branch(feature_id, root=repo)
    if not merge_result.ok:
        return False
    move_doc(feature_id, "completed", root=owner_root)
    # The feat→epic merge leaves the feature spec on the epic worktree. An
    # active copy there outranks a completed copy on the feature worktree.
    epic_entry = get_integration_worktree(trunk, "epic", epic_id)
    if epic_entry is not None and epic_entry.path.is_dir():
        epic_meta = list_board(epic_entry.path).by_id.get(feature_id)
        if epic_meta is not None and column_for_status(epic_meta.status) != "completed":
            move_doc(feature_id, "completed", root=epic_entry.path)
    if owner_root.resolve() != trunk.resolve():
        trunk_board = list_board(trunk)
        meta = trunk_board.by_id.get(feature_id)
        if meta is not None and column_for_status(meta.status) != "completed":
            move_doc(feature_id, "completed", root=trunk)

    _emit_feature_completed(feature_id, epic_id, repo)
    _record_satisfied_repair(feature_id, obligation, repo)
    _retire_feature_worktree(
        feature_id,
        epic_id,
        repo,
        merge_confirmed=True,
        current_obligation=obligation,
    )
    return True


def _current_open_review_postcheck_matches(
    feature_id: str,
    postcheck: dict[str, object] | None,
    *,
    root: Path,
) -> bool:
    """Require Boss to consume the fresh receipt for any scoped review repair."""

    from cascade.feature.repair import feature_repair_actions

    candidates = [
        action
        for action in feature_repair_actions(feature_id, root=root)
        if action.get("repair_route") == "open_review"
        and action.get("phase") not in {"blocked", "refused", "superseded"}
    ]
    if not candidates:
        return True
    current = max(candidates, key=lambda row: int(row.get("generation") or 0))
    return bool(
        isinstance(postcheck, dict)
        and postcheck.get("verified") is True
        and postcheck.get("repair_action_id") == current.get("action_id")
        and postcheck.get("repair_generation") == current.get("generation")
    )


def feature_completed_recorded(
    feature_id: WorkId, epic_id: WorkId, *, root: Path
) -> bool:
    """True when ``FeatureCompleted`` for ``feature_id`` is already on the epic feed."""

    events, _ = read_events(epic_id, 0, root=root)
    return any(
        event.type == "FeatureCompleted"
        and event.payload.get("feature_id") == feature_id
        for event in events
    )


def _emit_feature_completed(feature_id: str, epic_id: str, repo: Path) -> None:
    if feature_completed_recorded(feature_id, epic_id, root=repo):
        return
    append_event(
        epic_id,
        Event(
            type="FeatureCompleted",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": feature_id},
            dest=epic_id,
        ),
        root=repo,
    )


def _retire_feature_worktree(
    feature_id: WorkId,
    epic_id: WorkId | None,
    repo: Path,
    *,
    merge_confirmed: bool = False,
    current_obligation: CurrentFeatureObligation | None = None,
) -> None:
    """Best-effort cleanup after the feature is durably terminal.

    Cleanup must not turn a successful merge into a failed lifecycle action.  The
    workspace primitive refuses dirty, locked, non-canonical, or currently-used
    checkouts and preserves the integration branch for history/recovery.
    """

    from cascade.workspace.integration_worktree import (
        locate_trunk,
        prove_terminal_retirement,
        retire_integration_worktree,
    )

    if epic_id is None:
        return
    if current_obligation is not None and not current_obligation.satisfied:
        _LOG.warning(
            "could not retire completed feature worktree %s: current obligation %s",
            feature_id,
            current_obligation.reason or "is incomplete",
        )
        return
    trunk = locate_trunk(repo)
    proof = prove_terminal_retirement("feature", feature_id, trunk=trunk)
    if not proof.ok:
        _LOG.warning(
            "could not retire completed feature worktree %s: %s; %s",
            feature_id,
            proof.reason,
            proof.next_action,
        )
        return
    try:
        retire_integration_worktree(
            "feature",
            feature_id,
            merged_into=f"epic/{epic_id}",
            merge_confirmed=merge_confirmed,
            trunk=trunk,
        )
    except Exception:
        _LOG.exception("could not retire completed feature worktree %s", feature_id)


def current_feature_obligation(
    feature_id: str,
    *,
    root: Path,
    board=None,
    review_generation: int | None = None,
) -> CurrentFeatureObligation:
    """Evaluate the current delivery generation that may authorize closeout.

    This projection is called only while ``task_lifecycle_lock`` is held.  It
    does not poll the forge or acquire the review registry write lock.  The
    ``review_generation`` argument remains for API compatibility; a callback
    generation is never accepted in place of persisted review and target proof.
    """

    from cascade.feature.repair import feature_repair_actions
    from cascade.review import feature_delivery_view, review_enabled
    from cascade.workspace.integration_worktree import merged_board

    repo = resolve_root(root)
    delivery = feature_delivery_view(feature_id, root=repo)
    delivery_generation = int(delivery.get("generation") or 0)
    actions = feature_repair_actions(feature_id, root=root)
    live = [
        action
        for action in actions
        if action.get("phase") not in {"verified", "blocked", "superseded"}
        and not str(action.get("phase") or "").startswith(("blocked", "superseded"))
    ]
    if not live:
        if delivery.get("phase") in {
            "verified_integrated",
            "terminal_cancelled",
            "terminal_closed",
        }:
            return CurrentFeatureObligation(True, delivery_generation)
        if (
            delivery.get("phase") == "merge_verification_pending"
            and delivery.get("evidence_status") == "accepted_current_generation"
            and delivery.get("blocker") == "completion_event_missing"
        ):
            return CurrentFeatureObligation(True, delivery_generation)
        # Review-disabled delivery keeps the existing supervised local merge
        # path.  That path supplies its own ancestry/event evidence before
        # retirement; the shared projection cannot require the event that Boss
        # is responsible for emitting.
        if not review_enabled(repo):
            return CurrentFeatureObligation(True, delivery_generation)
        return CurrentFeatureObligation(
            False,
            delivery_generation,
            str(delivery.get("blocker") or "delivery_evidence_missing"),
        )
    current = max(live, key=lambda row: int(row.get("generation") or 0))
    generation = int(current.get("generation") or 0)
    if current.get("repair_route") == "open_review":
        return CurrentFeatureObligation(
            False,
            generation,
            str(
                current.get("next_action")
                or "independent_review_repair_postcheck_pending"
            ),
        )
    if any(
        action.get("phase") in {"prepared", "authority_recorded", "parent_enabled"}
        for action in live
    ):
        return CurrentFeatureObligation(False, generation, "admission is not persisted")
    board = board or merged_board(repo)
    child_ids = _child_task_ids(feature_id, board)
    if not child_ids or any(
        task_id not in board.by_id
        or board.by_id[task_id].status != "completed"
        or board.by_id[task_id].path.parent.name != "3_completed"
        for task_id in child_ids
    ):
        return CurrentFeatureObligation(
            False, generation, "child delivery is nonterminal"
        )
    from cascade.task.execution import execution_lease_is_live

    if any(execution_lease_is_live(task_id, root=root) for task_id in child_ids):
        return CurrentFeatureObligation(
            False, generation, "child delivery lease is live"
        )
    obligation_task_id = current.get("reserved_task_id") or current.get("task_id")
    if obligation_task_id not in child_ids:
        return CurrentFeatureObligation(
            False, generation, "repair child is not canonical"
        )
    events, _ = read_events(feature_id, 0, root=repo)
    repair_task_id = str(obligation_task_id)
    if not any(
        event.type == "TaskMerged" and event.payload.get("task_id") == repair_task_id
        for event in events
    ):
        return CurrentFeatureObligation(
            False, generation, "repair child lacks exact delivery evidence"
        )
    if _has_open_human_comments(feature_id, resolve_root(root)):
        return CurrentFeatureObligation(
            False, generation, "human comments are unresolved"
        )
    feature = board.by_id.get(feature_id)
    if feature is None or feature.approved_at is None:
        return CurrentFeatureObligation(False, generation, "approval is not current")
    for dependency_id in feature.depends_on:
        dependency = board.by_id.get(dependency_id)
        if dependency is None or dependency.status != "completed":
            return CurrentFeatureObligation(
                False, generation, "dependency is not current"
            )
    if review_enabled(repo):
        if delivery_generation != generation:
            return CurrentFeatureObligation(
                False, generation, "current_review_generation_mismatch"
            )
        if delivery.get("phase") == "verified_integrated" or (
            delivery.get("phase") == "merge_verification_pending"
            and delivery.get("evidence_status") == "accepted_current_generation"
            and delivery.get("blocker") == "completion_event_missing"
        ):
            return CurrentFeatureObligation(True, generation)
        return CurrentFeatureObligation(
            False,
            generation,
            str(delivery.get("blocker") or "delivery_evidence_missing"),
        )
    if feature.parent:
        parent_id = feature.parent
        source = f"feat/{feature_id}"
        target = f"epic/{parent_id}"
        check = subprocess.run(
            ["git", "merge-base", "--is-ancestor", source, target],
            cwd=resolve_root(root),
            capture_output=True,
            check=False,
        )
        if check.returncode == 0 and feature_completed_recorded(
            feature_id, parent_id, root=resolve_root(root)
        ):
            return CurrentFeatureObligation(True, generation)
    return CurrentFeatureObligation(
        False, generation, "local integration evidence is missing"
    )


def _record_satisfied_repair(
    feature_id: str, obligation: CurrentFeatureObligation, root: Path
) -> None:
    if not obligation.satisfied or not obligation.generation:
        return
    from cascade.feature.repair import mark_legacy_feature_repair_verified

    mark_legacy_feature_repair_verified(feature_id, obligation.generation, root=root)


def _feature_owner_root(feature_id: str, doc, repo: Path) -> Path:
    from cascade.workspace.integration_worktree import (
        get_integration_worktree,
        git_root_for_path,
        locate_trunk,
    )

    trunk = locate_trunk(repo)
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is not None and entry.path.is_dir():
        return entry.path
    try:
        return git_root_for_path(doc.meta.path)
    except GitError:
        return repo


def on_task_merged(task_id: WorkId, *, root: Path | None = None) -> None:
    """After a task merge, reconcile feature and epic completion from persisted state."""

    repo = resolve_root(root)
    try:
        task = read_doc(task_id, root=repo)
    except NotFound:
        return
    if task.meta.tier != "task":
        return
    from cascade.completion_reconcile import reconcile_completion_with_prompts

    reconcile_completion_with_prompts(root=repo)


def _rollup_gates_pass(
    feature_id: WorkId,
    body: str,
    board,
    repo: Path,
) -> bool:
    if _delivery_recovery_planning_pending(feature_id, repo):
        return False
    if not _all_child_tasks_completed(feature_id, board):
        return False
    if _has_open_human_comments(feature_id, repo):
        return False
    if not _closeout_present(body):
        return False
    return True


def _delivery_recovery_planning_pending(feature_id: str, root: Path) -> bool:
    """A recovered planning blockage must return control to its owning team.

    Ordinary closeout still needs no extra model turn. This boundary only
    applies after delivery recovery may have interrupted task decomposition.
    """
    event_type = "TaskDeliveryBlockageCleared"
    events, _ = read_events(feature_id, 0, root=root)
    if not any(e.type == event_type for e in events):
        return False
    from cascade.feature.checkpoint import thread_config
    from cascade.feature.graph import ensure_feature_graph
    from cascade.workspace.kickoff import graph_turn_owner_is_live

    snapshot = ensure_feature_graph(feature_id, root=root).get_state(
        thread_config(feature_id)
    )
    offset = int((snapshot.values or {}).get("last_queue_offset") or 0)
    unread, _ = read_events(feature_id, offset, root=root)
    return (
        any(e.type == event_type for e in unread)
        or bool(snapshot.next)
        or graph_turn_owner_is_live(feature_id)
    )


def _child_task_ids(feature_id: WorkId, board) -> set[WorkId]:
    feature = board.by_id[feature_id]
    ids = set(feature.children)
    for meta in board.by_id.values():
        if meta.tier == "task" and meta.parent == feature_id:
            ids.add(meta.id)
    return ids


def _all_child_tasks_completed(feature_id: WorkId, board) -> bool:
    for task_id in _child_task_ids(feature_id, board):
        meta = board.by_id.get(task_id)
        if meta is None or meta.tier != "task":
            return False
        if meta.status != "completed":
            return False
        if column_for_status(meta.status) != "completed":
            return False
        if meta.path.parent.name != "3_completed":
            return False
    return True


def _synthesized_closeout(feature_id: WorkId, board) -> str | None:
    """Return a stable, auditable fallback summary for a finished feature."""

    task_ids = sorted(_child_task_ids(feature_id, board))
    if not task_ids:
        return None
    completed = []
    for task_id in task_ids:
        meta = board.by_id.get(task_id)
        if meta is None:
            return None
        completed.append(f"`{task_id}` ({meta.title})")
    return "Completed child work: " + ", ".join(completed) + "."


def _has_open_human_comments(feature_id: WorkId, repo: Path) -> bool:
    for row in read_comments(feature_id, root=repo):
        if row.state == "open" and row.author == "human":
            return True
    return False


def _closeout_present(body: str) -> bool:
    return bool(_read_closeout_paragraph(body))


def _read_closeout_paragraph(body: str) -> str | None:
    match = _CLOSEOUT_HEADING.search(body)
    if match is None:
        return None
    rest = body[match.end() :]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    next_match = _NEXT_SECTION.search(rest)
    section = rest[: next_match.start()] if next_match else rest
    text = section.strip()
    return text or None


def _upsert_closeout_section(body: str, paragraph: str) -> str:
    para = paragraph.strip()
    new_section = f"## Closeout\n\n{para}\n"
    match = _CLOSEOUT_HEADING.search(body)
    if match is not None:
        rest = body[match.end() :]
        next_match = _NEXT_SECTION.search(rest)
        if next_match is not None:
            tail_start = match.end() + next_match.start()
            return (
                body[: match.start()] + new_section.rstrip() + "\n" + body[tail_start:]
            )
        return body[: match.start()] + new_section
    trimmed = body.rstrip()
    if trimmed:
        return trimmed + "\n\n" + new_section
    return new_section
