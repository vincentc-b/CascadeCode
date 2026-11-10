"""Dispatch law. Planning graphs do not call move_doc; this module does."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import head_sha
from cascade.board.paths import column_dir
from cascade.board.gitutil import commit_paths, has_git
from cascade.board.store import move_doc, read_doc, save_doc, write_doc
from cascade.board.types import BoardIndex, WorkMeta
from cascade.dependency_evaluation import evaluate_dependencies
from cascade.agent.discovery.inventory import get_provider_inventory
from cascade.agent.capability_contract import EffectiveSelectionBatch
from cascade.agent.preflight import (
    ProviderCapabilityBatchPreflight,
)
from cascade.agent.execution_preflight import record_failed_provider_action
from cascade.agent.flex_continuation_contract import ActionKind
from cascade.agent.selection_preflight import RuntimeSelection, evaluate_work_selection
from cascade.board.parse import parse_doc
from cascade.epic.activation import _drop_stale_copies, activate_epic_on_worktree
from cascade.planning_action_dependencies import evaluate_action_dependencies
from cascade.watchdog.config import task_parallelism
from cascade.watchdog.events import append_event
from cascade.watchdog.hooks import invoke_boot
from cascade.watchdog.lock import process_lock
from cascade.watchdog.skills import (
    SkillPathError,
    effective_skill_paths,
    rewrite_skills_section,
)
from cascade.watchdog.types import DispatchResult, Event, Principal
from cascade.workspace.backlog_snapshot import resolve_validated_epic_activation_sha
from cascade.workspace.integration_worktree import (
    create_integration_worktree,
    doc_filesystem_root,
    get_integration_worktree,
    integration_branch,
    merged_board,
    refresh_merged_board,
    unregister_missing_integration_worktree,
)

_OPEN = {"backlog", "ready_to_plan"}


def activate_epic(
    work_id: str, by: Principal, *, root: Path | None = None
) -> DispatchResult:
    """Human-only epic activation. Success lands the file in 2_active with status active."""

    repo = resolve_root(root)
    with process_lock:
        result = _activate_epic(work_id, by, repo)
    return _boot_after(result, "epic", work_id, by, repo)


def dispatch_feature(
    work_id: str,
    by: Principal,
    *,
    root: Path | None = None,
    expected_parent: str | None = None,
) -> DispatchResult:
    """Human or Boss starts feature planning. Success status is active, not ready_to_plan."""

    repo = resolve_root(root)
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    with task_lifecycle_lock(root=repo):
        result = _dispatch_feature(work_id, by, repo, expected_parent=expected_parent)
    return _boot_after(result, "feature", work_id, by, repo)


def dispatch_task(
    work_id: str,
    by: Principal,
    skills: list[Path] | None = None,
    *,
    root: Path | None = None,
    expected_parent: str | None = None,
) -> DispatchResult:
    """Human or Boss starts a task when dependencies are done and a slot is free.

    A `blocked` task already in `2_active` is the legal restart. `skills is not None`
    replaces the skill list on the same write as the transition to `active`.
    Over cap: the file stays put and no TaskDispatched event is written.
    """

    repo = resolve_root(root)
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    with task_lifecycle_lock(root=repo):
        result = _dispatch_task(
            work_id, by, skills, repo, expected_parent=expected_parent
        )
        if result.ok:
            from cascade.task.execution import _read, _write

            records = _read(repo)
            row = records.get(work_id, {})
            for revision in row.get("contract_revisions", []):
                revision["consumed"] = True
            if row:
                records[work_id] = row
                _write(repo, records)
    return _boot_after(result, "task", work_id, by, repo)


def _boot_after(
    result: DispatchResult,
    tier: str,
    work_id: str,
    by: Principal,
    root: Path,
) -> DispatchResult:
    """Boot runs after the process lock is released so a hook can tick without deadlock."""

    if result.ok:
        from cascade.provider_recovery_replay import record_canonical_replay_transition

        if not record_canonical_replay_transition(result, work_id=work_id, root=root):
            return result
        if tier == "task":
            from cascade.task.execution import mark_queued

            mark_queued(work_id, root=root)
        invoke_boot(tier, work_id)
        from cascade.workspace.kickoff import kickoff_turn
        from cascade.workspace.types import KickoffReason
        from cascade.provider_recovery_replay import kickoff_receipt

        kind = "activate" if tier == "epic" else "dispatch"
        continuation = kickoff_receipt(work_id, root)
        kickoff_turn(
            KickoffReason(
                kind=kind,  # type: ignore[arg-type]
                work_id=work_id,
                by=by,  # type: ignore[arg-type]
                root=root,
                continuation_receipt_id=(continuation[0] if continuation else None),
                continuation_handoff_id=(continuation[1] if continuation else None),
            )
        )
    return result


def _activate_epic(work_id: str, by: str, root: Path) -> DispatchResult:
    if by != "human":
        return _fail("unauthorized")
    board = refresh_merged_board(root)
    meta = board.by_id.get(work_id)
    if meta is None:
        return _fail("not_found")
    if meta.tier != "epic" or meta.status not in _OPEN:
        return _fail("bad_state")
    # A reviewed retry is a new planning run.  It must not attach to children
    # that belong to the archived run (or to a partially restored board).
    if any(
        candidate.parent == work_id and candidate.status != "backlog"
        for candidate in board.by_id.values()
    ):
        return _fail("existing_child_work")
    from cascade.epic.return_graph import read_manifest, reactivate_graph

    returned_manifest = read_manifest(root, work_id)
    returning = (
        returned_manifest is not None and returned_manifest["state"] == "returned"
    )
    if (
        not returning
        and get_integration_worktree(root, "epic", work_id) is not None
        and not unregister_missing_integration_worktree(
            "epic", work_id, trunk=root, require_missing_branch=True
        )
    ):
        return _fail("existing_activation_run")
    if not _deps_met(board, meta, root=root):
        return _fail("unmet_deps")
    if refusal := _provider_preflight_refusal(meta, by=by, root=root):
        return refusal
    if returning:
        reactivate_graph(work_id, root=root)
        run_id = _begin_epic_activation_run(work_id, root)
        event = _emit(
            root,
            work_id,
            "EpicActivated",
            {"epic_id": work_id, "by": by, "run_id": run_id},
        )
        return DispatchResult(ok=True, reason=None, event=event)
    if not has_git(root):
        move_doc(work_id, "active", root=root)
        run_id = _begin_epic_activation_run(work_id, root)
        event = _emit(
            root,
            work_id,
            "EpicActivated",
            {"epic_id": work_id, "by": by, "run_id": run_id},
        )
        return DispatchResult(ok=True, reason=None, event=event)
    base_sha = resolve_validated_epic_activation_sha(work_id, trunk=root)
    if base_sha is None:
        return _fail("brief_not_on_trunk")
    if head_sha(root) is None:
        return _fail("bad_state")
    branch = integration_branch("epic", work_id)
    epic_wt = create_integration_worktree(
        "epic",
        work_id,
        branch=branch,
        base_ref=base_sha,
        trunk=root,
    )
    activate_epic_on_worktree(work_id, trunk=root, epic_wt=epic_wt)
    run_id = _begin_epic_activation_run(work_id, root)
    event = _emit(
        root, work_id, "EpicActivated", {"epic_id": work_id, "by": by, "run_id": run_id}
    )
    return DispatchResult(ok=True, reason=None, event=event)


def _begin_epic_activation_run(work_id: str, root: Path) -> str:
    """Archive the prior graph state before the new activation boot resolves pins."""

    from cascade.epic.checkpoint import begin_activation_run
    from cascade.epic.graph import clear_epic_graph_session

    clear_epic_graph_session(work_id, root=root)
    return begin_activation_run(work_id, root=root)


def _dispatch_feature(
    work_id: str,
    by: str,
    root: Path,
    *,
    expected_parent: str | None = None,
) -> DispatchResult:
    if by not in ("human", "boss"):
        return _fail("unauthorized")
    dependency_evidence = evaluate_action_dependencies(work_id, root=root)
    if dependency_evidence.owner is None:
        if dependency_evidence.board is not None:
            return _fail("not_found")
        return _fail("dependency_status_unavailable")
    assert dependency_evidence.board is not None
    board = dependency_evidence.board
    meta = dependency_evidence.owner
    if meta is None:
        return _fail("not_found")
    if meta.tier != "feature" or meta.status not in _OPEN:
        return _fail("bad_state")
    if not meta.parent:
        return _fail("bad_state")
    if expected_parent is not None and meta.parent != expected_parent:
        return _fail("feature_parent_changed")
    if dependency_evidence.outcome != "satisfied":
        return _fail(dependency_evidence.outcome)
    from cascade.feature.readiness import (
        compute_feature_readiness,
        dispatch_refusal_from_readiness,
    )

    readiness = compute_feature_readiness(work_id, root=root, board=board)
    if readiness is None:
        return _fail("not_found")
    if reason := dispatch_refusal_from_readiness(readiness):
        return _fail(reason)
    if refusal := _provider_preflight_refusal(meta, by=by, root=root):
        return refusal
    from cascade.lifecycle_review_gate import require_lifecycle_review_gate
    from cascade.workspace.architecture_review import ArchitectureProposalError

    try:
        require_lifecycle_review_gate(work_id, "dispatch", root=root)
    except ArchitectureProposalError as exc:
        return _fail(exc.code, detail=str(exc))

    from cascade.stacked_dispatch import ensure_feature_dispatch_selection

    dispatch_plan = ensure_feature_dispatch_selection(work_id, meta, board, root=root)
    if not dispatch_plan.ok:
        return _fail(dispatch_plan.reason or "bad_state")
    assert dispatch_plan.selection is not None

    if not has_git(root):
        move_doc(work_id, "active", root=root)
        event = _emit(
            root,
            work_id,
            "FeatureReadyToPlan",
            {"id": work_id, "feature_id": work_id, "by": by},
        )
        return DispatchResult(ok=True, reason=None, event=event)

    epic_id = meta.parent
    epic_wt = get_integration_worktree(root, "epic", epic_id)
    if epic_wt is None:
        return _fail("bad_state")
    base_ref = dispatch_plan.selection.base_branch
    if head_sha(root) is None:
        return _fail("bad_state")

    feat_branch = integration_branch("feature", work_id)
    feat_wt = create_integration_worktree(
        "feature",
        work_id,
        branch=feat_branch,
        base_ref=base_ref,
        trunk=root,
    )

    _relocate_active(work_id, dest_root=feat_wt.path, trunk=root)

    event = _emit(
        root,
        work_id,
        "FeatureReadyToPlan",
        {"id": work_id, "feature_id": work_id, "by": by},
    )
    return DispatchResult(ok=True, reason=None, event=event)


def _dispatch_task(
    work_id: str,
    by: str,
    skills: list[Path] | None,
    root: Path,
    *,
    expected_parent: str | None = None,
) -> DispatchResult:
    if by not in ("human", "boss"):
        return _fail("unauthorized")
    if isinstance(skills, (str, Path)):
        raise TypeError("skills must be a list of paths or None")
    dependency_evidence = evaluate_action_dependencies(work_id, root=root)
    if dependency_evidence.owner is None:
        if dependency_evidence.board is not None:
            return _fail("not_found")
        return _fail("dependency_status_unavailable")
    assert dependency_evidence.board is not None
    board = dependency_evidence.board
    meta = dependency_evidence.owner
    if meta is None:
        return _fail("not_found")
    if expected_parent is not None and meta.parent != expected_parent:
        return _fail("task_parent_changed")
    if not _task_can_start(meta):
        return _fail("bad_state")
    from cascade.task.execution import execution_lease_is_live

    if execution_lease_is_live(work_id, root=root):
        return _fail("execution_owner_live")
    if meta.status == "blocked":
        from cascade.task.execution import execution_view
        from cascade.feature.recovery import recovery_status

        execution = execution_view(work_id, root=root) or {}
        if (
            execution.get("phase") == "terminal"
            and recovery_status(work_id, feature_id=meta.parent, root=root)["action"]
            != "retry"
        ):
            return _fail("task_contract_revision_required")
    from cascade.task.guard import contract_scope_blocker
    from cascade.workspace.doc_root import read_doc_resolved

    scope_blocker = contract_scope_blocker(read_doc_resolved(work_id, root=root).body)
    if scope_blocker:
        _emit(
            root,
            meta.parent or work_id,
            "TaskScopeBlocked",
            {"task_id": work_id, **scope_blocker},
        )
        return _fail("task_scope_denied")
    if not meta.parent:
        return _fail("bad_state")
    parent = board.by_id.get(meta.parent)
    if parent is None:
        return _fail("bad_state")
    from cascade.cancellation_feedback import cancellation_dispatch_gated

    if cancellation_dispatch_gated(parent):
        return _fail("parent_cancellation_pending")
    if dependency_evidence.outcome != "satisfied":
        return _fail(dependency_evidence.outcome)
    if _dependency_review_pending(board, meta, root=root):
        return _fail("feature_awaiting_merge")
    if _active_task_count(board, root=root) >= task_parallelism(root):
        return _fail("cap")
    from cascade.comments.gate import refusal_if_blocked

    if blocked := refusal_if_blocked(work_id, root=root):
        return _fail(blocked)
    if refusal := _provider_preflight_refusal(meta, by=by, root=root):
        return refusal

    from cascade.lifecycle_review_gate import require_lifecycle_review_gate
    from cascade.workspace.architecture_review import ArchitectureProposalError

    try:
        require_lifecycle_review_gate(work_id, "dispatch", root=root)
    except ArchitectureProposalError as exc:
        return _fail(exc.code, detail=str(exc))

    if not has_git(root):
        move_doc(work_id, "active", root=root)
        event = _emit(
            root,
            work_id,
            "TaskDispatched",
            {
                "id": work_id,
                "task_id": work_id,
                "feature_id": meta.parent,
                "by": by,
                "skills": [],
            },
        )
        return DispatchResult(ok=True, reason=None, event=event)

    feat_id = meta.parent
    feat_wt = get_integration_worktree(root, "feature", feat_id)
    if feat_wt is None:
        return _fail("bad_state")

    # A new contract cannot authorize overwriting evidence from an old run.
    # Preserve dirty work for the owning team's scoped recovery operation.
    task_wt = get_integration_worktree(root, "task", work_id)
    if task_wt is not None and task_wt.path.is_dir():
        import subprocess

        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=task_wt.path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if branch != integration_branch("task", work_id):
            return _fail("task_worktree_branch_mismatch")
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=task_wt.path,
            capture_output=True,
            text=True,
            check=True,
        )
        if status.stdout.strip():
            from cascade.task.git_tools import _assert_commit_paths_allowed
            from cascade.task.guard import TaskToolDenied

            try:
                _assert_commit_paths_allowed(work_id, task_wt.path, board_root=root)
            except TaskToolDenied as exc:
                _emit(
                    root,
                    meta.parent,
                    "TaskScopeBlocked",
                    {
                        "task_id": work_id,
                        "reason": "task_worktree_scope_denied",
                        "detail": str(exc),
                        "next_step": "Preserved work includes protected paths. The owning planning team must resolve those paths before Task retry.",
                    },
                )
                return _fail("task_worktree_scope_denied")
            _emit(
                root,
                work_id,
                "TaskWorkspacePreserved",
                {
                    "task_id": work_id,
                    "instruction": "Resume the existing scoped changes; commit them before final validation. No work was discarded.",
                },
            )

    chosen = list(meta.skills) if skills is None else [Path(item) for item in skills]
    try:
        skill_paths = effective_skill_paths(root, chosen)
    except SkillPathError:
        return _fail("bad_state")

    # A Feature Team commonly mints several Tasks while it continues editing
    # the Feature plan.  The revision captured at mint time is therefore only
    # a draft pin.  Refresh it immediately before cutting the execution branch
    # so a not-yet-started Task cannot fail merely because a sibling was added
    # or the parent plan was clarified.
    meta = _refresh_task_parent_pin(
        work_id,
        feat_id,
        feature_root=feat_wt.path,
        trunk=root,
    )

    feat_branch = integration_branch("feature", feat_id)
    from cascade.task.worktree import create_task_worktree

    create_task_worktree(
        work_id,
        root=root,
        parent_rev=meta.parent_rev,
        skills=skill_paths,
        base_ref=feat_branch,
    )

    feature_root = feat_wt.path
    _place_task_active(
        feature_root,
        work_id,
        None if skills is None else skill_paths,
        trunk=root,
    )
    event = _emit(
        root,
        work_id,
        "TaskDispatched",
        {
            "id": work_id,
            "task_id": work_id,
            "feature_id": feat_id,
            "by": by,
            "skills": skill_paths,
            "instruction": (
                "Read the Task and pinned Feature plans, implement the scoped change, "
                "run the relevant tests, and leave a deliverable commit on the Task branch. "
                "A finished turn with only board lifecycle changes fails closed."
            ),
        },
    )
    return DispatchResult(ok=True, reason=None, event=event)


def _refresh_task_parent_pin(
    task_id: str,
    feature_id: str,
    *,
    feature_root: Path,
    trunk: Path,
) -> WorkMeta:
    """Commit the live Feature revision onto a Task before its branch is cut."""

    source_root = doc_filesystem_root(task_id, trunk=trunk)
    task = read_doc(task_id, root=source_root)
    feature = read_doc(feature_id, root=feature_root)
    task.meta.parent_rev = feature.sha
    write_doc(task, root=source_root)
    return read_doc(task_id, root=source_root).meta


def _task_can_start(meta: WorkMeta) -> bool:
    """Backlog/ready_to_plan, or a blocked task already sitting in 2_active."""

    if meta.tier != "task" or not meta.parent:
        return False
    if meta.status in _OPEN:
        return True
    return meta.status == "blocked" and meta.path.parent.name == "2_active"


def _place_task_active(
    board_root: Path,
    work_id: str,
    skill_paths: list[str] | None,
    *,
    trunk: Path,
) -> None:
    """One write: status active in 2_active, with a skill override applied only here."""

    source_root = doc_filesystem_root(work_id, trunk=trunk)
    doc = read_doc(work_id, root=source_root)
    previous = doc.meta.path.resolve()
    if skill_paths is not None:
        doc.meta.skills = [Path(item) for item in skill_paths]
        doc.body = rewrite_skills_section(doc.body, skill_paths)
    doc.meta.status = "active"
    doc.meta.path = (
        board_root / column_dir("task", "active") / previous.name
    ).resolve()
    if source_root.resolve() == board_root.resolve():
        save_doc(doc, previous_path=previous, root=board_root)
        return
    _drop_stale_copies(
        work_id,
        tier=doc.meta.tier,
        keep=doc.meta.path,
        board_root=board_root,
    )
    write_doc(doc, root=board_root)
    if previous.exists() and previous != doc.meta.path.resolve():
        previous.unlink()
        if has_git(source_root):
            commit_paths(source_root, [previous], f"docs: relocate {work_id}")


def _deps_met(board: BoardIndex, meta: WorkMeta, *, root: Path) -> bool:
    if not evaluate_dependencies(meta, root=root, board=board).satisfied:
        return False
    for dep_id in meta.depends_on:
        dep = board.by_id[dep_id]
        if dep.tier == "feature":
            from cascade.review import feature_review_pending

            if feature_review_pending(dep_id, root=root):
                return False
    return True


def _dependency_review_pending(
    board: BoardIndex, meta: WorkMeta, *, root: Path
) -> bool:
    """Keep review delivery separate from lifecycle dependency readiness."""

    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is not None and dep.tier == "feature":
            from cascade.review import feature_review_pending

            if feature_review_pending(dep_id, root=root):
                return True
    return False


def _active_task_count(board: BoardIndex, *, root: Path | None = None) -> int:
    count = 0
    for meta in board.by_id.values():
        if (
            meta.tier == "task"
            and meta.status == "active"
            and meta.path.parent.name == "2_active"
        ):
            if root is not None:
                from cascade.task.execution import execution_view

                execution = execution_view(meta.id, root=root) or {}
                if execution.get("phase") in {
                    "awaiting_merge",
                    "merge_blocked",
                    "terminal",
                }:
                    continue
            count += 1
    return count


def _emit(root: Path, dest: str, event_type: str, payload: dict[str, object]) -> Event:
    event = Event(
        type=event_type,
        ts=datetime.now(timezone.utc),
        payload=payload,
        dest=dest,
    )
    append_event(dest, event, root=root)
    return event


def _provider_preflight_refusal(
    meta: WorkMeta,
    *,
    by: str,
    root: Path,
) -> DispatchResult | None:
    """Check every role the dispatch will start before any durable work begins.

    Resolution is fail closed: incomplete legacy documents are represented as
    safe selection issues rather than silently skipping the gate.
    """

    if meta.tier not in ("epic", "feature", "task"):
        return None
    inventory = get_provider_inventory()
    action_kind = _failed_action_kind(meta, by)
    action = action_kind or f"{meta.tier}_dispatch"
    try:
        doc = parse_doc(meta.path)
        if not _same_dispatch_selection(meta, doc.meta):
            raise ValueError("owning document provenance changed")
    except Exception:
        # The merged board is only an index.  If its selected owning document
        # disappeared or changed before admission, project every resolved role
        # through the shared stale-selection path instead of trusting the copy.
        base = evaluate_work_selection(
            meta,
            root=root,
            inventory=inventory,
            action=action,
        )
        evaluated = evaluate_work_selection(
            meta,
            root=root,
            inventory=inventory,
            action=action,
            runtime_selections=(
                RuntimeSelection(
                    role=item.role,
                    provider="__stale__",
                    model_id="__stale__",
                )
                for item in base.selections.selections
            ),
        )
    else:
        evaluated = evaluate_work_selection(
            doc,
            root=root,
            inventory=inventory,
            action=action,
        )
    result = evaluated.result
    if result.supported:
        return None
    if action_kind is not None:
        try:
            record_failed_provider_action(
                meta.id,
                tier=meta.tier,
                action_kind=action_kind,
                result=result,
                root=root,
                original_actor=by,
                replay_arguments={
                    "by": by,
                    **({"feature_id": meta.parent} if meta.parent else {}),
                },
            )
        except ValueError:
            # An incomplete/stale selection is still refused, but cannot mint
            # the concrete identity required by Flex continuation.
            pass
    reason = (
        "provider_preflight_blocked"
        if result.outcome == "blocked"
        else "provider_preflight_unavailable"
    )
    return _fail(reason, preflight=result, selections=evaluated.selections)


def _failed_action_kind(meta: WorkMeta, by: str) -> ActionKind | None:
    """Map only the four continuation adapters; ordinary Task dispatch is out."""

    if meta.tier == "epic":
        return "epic_activation"
    if meta.tier == "feature":
        return "approval_dispatch" if by == "boss" else "feature_dispatch"
    if meta.tier == "task" and meta.status == "blocked":
        return "task_retry"
    if meta.tier == "task" and by == "boss":
        return "approval_dispatch"
    return None


def _same_dispatch_selection(indexed: WorkMeta, owning: WorkMeta) -> bool:
    """Confirm the board snapshot still names the reviewed owning selection."""

    return (
        owning.id == indexed.id
        and owning.tier == indexed.tier
        and owning.path.resolve() == indexed.path.resolve()
        and owning.parent == indexed.parent
        and owning.parent_rev == indexed.parent_rev
        and owning.provider == indexed.provider
        and owning.model == indexed.model
        and owning.models == indexed.models
        and owning.reasoning == indexed.reasoning
        and owning.flex_mode == indexed.flex_mode
    )


def _fail(
    reason: str,
    *,
    preflight: ProviderCapabilityBatchPreflight | None = None,
    selections: EffectiveSelectionBatch | None = None,
    detail: str | None = None,
) -> DispatchResult:
    return DispatchResult(
        ok=False,
        reason=reason,
        event=None,
        preflight=preflight,
        selections=selections,
        detail=detail,
    )


def _relocate_active(work_id: str, *, dest_root: Path, trunk: Path) -> None:
    """Move a work doc into ``dest_root`` ``2_active`` and drop the prior copy."""

    source_root = doc_filesystem_root(work_id, trunk=trunk)
    doc = read_doc(work_id, root=source_root)
    old_path = doc.meta.path.resolve()
    tier = doc.meta.tier
    if tier == "feature":
        # The source selected for relocation may be a stale copy from an
        # integration branch. Preserve the durable approval from the merged
        # supervisor view in the new active document.
        approved = merged_board(trunk).by_id.get(work_id)
        if approved is not None:
            doc.meta.approved_at = approved.approved_at
    doc.meta.status = "active"
    doc.meta.path = (dest_root / column_dir(tier, "active") / old_path.name).resolve()
    _drop_stale_copies(
        work_id,
        tier=doc.meta.tier,
        keep=doc.meta.path,
        board_root=dest_root,
    )
    write_doc(doc, root=dest_root)
    if old_path.exists() and old_path != doc.meta.path.resolve():
        old_path.unlink()
        if has_git(source_root) and source_root.resolve() != dest_root.resolve():
            commit_paths(source_root, [old_path], f"docs: relocate {work_id}")
