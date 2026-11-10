"""Production graph discovery and lossless local backlog projection.

Returned documents live beside the transition journal, not on operator trunk.
Original branches, worktrees, checkpoints and conversations remain untouched.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from cascade.board.context import resolve_tracking_root
from cascade.board.parse import parse_doc, parse_text, render_doc
from cascade.board.types import BoardIndex
from cascade.epic.return_eligibility import (
    ReturnEligibilityInput,
    ReturnGraphMember,
    evaluate_return_eligibility,
)
from cascade.epic.return_transaction import (
    ActiveToBacklogTransaction,
    TransitionUnsafe,
    _durable_write,
    emit_transition_audit,
)
from cascade.workspace.integration_worktree import (
    locate_trunk,
    merged_board,
    load_registry_readonly,
    invalidate_merged_board,
)


def return_home(root: Path, epic_id: str) -> Path:
    # IDs come from an existing board member, but still confine external input.
    from cascade.board.work_ids import tier_of_work_id

    if "/" in epic_id or ".." in epic_id or tier_of_work_id(epic_id) != "epic":
        raise ValueError("invalid epic id")
    return (
        locate_trunk(resolve_tracking_root(root))
        / ".cascade"
        / "epic-returns"
        / epic_id
    )


def read_manifest(root: Path, epic_id: str) -> dict | None:
    path = return_home(root, epic_id) / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else None


def returned_root_for_path(root: Path, path: Path) -> Path | None:
    home = locate_trunk(resolve_tracking_root(root)) / ".cascade" / "epic-returns"
    try:
        relative = path.resolve().relative_to(home.resolve())
    except ValueError:
        return None
    return home / relative.parts[0] if len(relative.parts) > 1 else None


def project_returns(root: Path, board: BoardIndex) -> None:
    home = root / ".cascade" / "epic-returns"
    if not home.exists():
        return
    live_boards = {}
    for path in sorted(home.glob("*/manifest.json")):
        manifest = json.loads(path.read_text())
        if manifest["state"] not in {"returning", "returned", "activated"}:
            continue
        for row in manifest["members"]:
            if manifest["state"] == "activated":
                from cascade.board.store import list_board

                live_root = Path(row["live_root"])
                if live_root not in live_boards:
                    live_boards[live_root] = list_board(live_root)
                candidate = live_boards[live_root].by_id.get(row["id"])
                if candidate is not None and candidate.status == "backlog":
                    board.by_id[candidate.id] = candidate
                continue
            doc = parse_doc(path.parent / row["backlog_path"])
            board.by_id[doc.meta.id] = doc.meta


def _members(board: BoardIndex, epic_id: str):
    ids = {epic_id}
    while True:
        expanded = ids | {m.id for m in board.by_id.values() if m.parent in ids}
        if expanded == ids:
            break
        ids = expanded
    members = [board.by_id[id] for id in sorted(ids) if id in board.by_id]
    complete = bool(members)
    for m in members:
        complete &= all(
            child in ids and child in board.by_id and board.by_id[child].parent == m.id
            for child in m.children
        )
        if m.id != epic_id:
            parent = board.by_id.get(m.parent)
            complete &= parent is not None and (parent.tier, m.tier) in {
                ("epic", "feature"),
                ("feature", "task"),
            }
    return members, bool(complete)


def load_snapshot(
    epic_id: str, *, root: Path, board: BoardIndex | None = None
) -> ReturnEligibilityInput:
    from cascade.epic.lifecycle_gate import lifecycle_gate
    from cascade.workspace.kickoff import graph_turn_owner_is_live
    from cascade.task.execution import execution_view

    root = locate_trunk(resolve_tracking_root(root))
    board = board if board is not None else merged_board(root)
    epic = board.by_id.get(epic_id)
    members, complete = _members(board, epic_id)
    facts = []
    registry = {w.work_id: w for w in load_registry_readonly(root)}
    for m in members:
        contents = m.path.read_bytes()
        digest = hashlib.sha256(contents).hexdigest()
        wt = registry.get(m.id)
        # Unactivated descendants have mint provenance (parent + saved source),
        # not an activation event. Their absence of a run is not missing history.
        provenance = (
            f"{wt.branch}@{wt.base_sha}" if wt else f"plan:{m.parent or m.id}:{digest}"
        )
        execution = execution_view(m.id, root=root) if m.tier == "task" else None
        busy_task = bool(execution and execution.get("phase") in {"queued", "running"})
        facts.append(
            ReturnGraphMember(
                m.id,
                m.tier,
                m.parent,
                digest,
                provenance,
                lifecycle_gate().turns_quiesced(m.id)
                and not graph_turn_owner_is_live(m.id)
                and not busy_task,
                m.status == "cancelling",
                True,
                True,
            )
        )
    return ReturnEligibilityInput(
        epic_id,
        epic.tier if epic else None,
        epic.status if epic else None,
        bool(epic and epic.status == "cancelling"),
        tuple(facts),
        complete,
        next((m.source_revision for m in facts if m.id == epic_id), None),
        tuple(sorted(m.id for m in facts)),
        False,
    )


def execute_return(
    epic_id: str, request_id: str, *, root: Path, gate=None, timeout=0.0
):
    from cascade.epic.return_command import ReturnEpicCommandResult
    from cascade.epic.lifecycle_gate import lifecycle_gate
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    root = locate_trunk(resolve_tracking_root(root))
    home = return_home(root, epic_id)
    # Dispatch and planning stores use this same process/cross-process lock.
    with task_lifecycle_lock(root=root):
        from cascade.workspace.integration_worktree import refresh_merged_board

        board = refresh_merged_board(root)
        manifest = read_manifest(root, epic_id)
        if (
            manifest
            and manifest["state"] == "activated"
            and manifest["request_id"] == request_id
        ):
            # A delayed retry belongs to the old run, not a fresh return order.
            return ReturnEpicCommandResult(True, epic_id, request_id)
        if manifest and manifest["state"] == "returned":
            return ReturnEpicCommandResult(
                True,
                epic_id,
                request_id,
                eligibility=evaluate_return_eligibility(
                    load_snapshot(epic_id, root=root)
                ),
            )
        snapshot = load_snapshot(epic_id, root=root, board=board)
        eligibility = evaluate_return_eligibility(snapshot)
        ids = tuple(m.id for m in snapshot.graph or () if m.id)
        if manifest and manifest["state"] == "returning":
            ids = tuple(row["id"] for row in manifest["members"])
        with (gate or lifecycle_gate()).transition(
            epic_id, ids, timeout=timeout
        ) as quiet:
            if not quiet:
                from cascade.epic.return_command import _quiescence_refusal

                return ReturnEpicCommandResult(
                    False,
                    epic_id,
                    request_id,
                    eligibility=_quiescence_refusal(
                        evaluate_return_eligibility(snapshot)
                    ),
                )
            if manifest is None or manifest["state"] == "activated":
                board = refresh_merged_board(root)
                snapshot = load_snapshot(epic_id, root=root, board=board)
                eligibility = evaluate_return_eligibility(snapshot)
                if not eligibility.eligible:
                    return ReturnEpicCommandResult(
                        False, epic_id, request_id, eligibility=eligibility
                    )
                if tuple(sorted(m.id for m in snapshot.graph or ())) != tuple(
                    sorted(ids)
                ):
                    raise TransitionUnsafe("descendant graph changed during return")
                rows = []
                for id in ids:
                    meta = board.by_id[id]
                    original = meta.path.read_text()
                    doc = parse_text(original, meta.path)
                    folder = {"epic": "epics", "feature": "features", "task": "tasks"}[
                        meta.tier
                    ]
                    relative = f"docs/{folder}/1_backlog/{meta.path.name}"
                    doc.meta = replace(
                        doc.meta,
                        status="backlog",
                        path=home / relative,
                        monitoring_blockers=[],
                    )
                    rows.append(
                        {
                            "id": id,
                            "backlog_path": relative,
                            "original_path": str(meta.path),
                            "original": original,
                            "backlog": render_doc(doc),
                        }
                    )
                # Stage a complete graph before publishing its durable intent.
                # An interrupted intent still projects backlog and blocks dispatch.
                for row in rows:
                    _durable_write(home / row["backlog_path"], row["backlog"].encode())
                manifest = {
                    "state": "returning",
                    "request_id": request_id,
                    "members": rows,
                }
                _durable_write(home / "manifest.json", json.dumps(manifest).encode())
            run_home = (
                home
                / "runs"
                / hashlib.sha256(manifest["request_id"].encode()).hexdigest()
            )
            _durable_write(run_home / "manifest.json", json.dumps(manifest).encode())
            transaction = ActiveToBacklogTransaction(
                root=run_home, epic_id=epic_id, request_id=manifest["request_id"]
            )

            def preserve():
                for row in manifest["members"]:
                    _durable_write(
                        run_home / "history" / f"{row['id']}.md",
                        row["original"].encode(),
                    )

            def restore():
                for row in manifest["members"]:
                    _durable_write(home / row["backlog_path"], row["backlog"].encode())

            def publish():
                manifest["state"] = "returned"
                _durable_write(home / "manifest.json", json.dumps(manifest).encode())
                invalidate_merged_board(root)

            # Sources, Git refs and worktrees are retained verbatim. Only the
            # fully staged local projection changes; admission remains closed.
            journal = transaction.execute(
                assert_safe=lambda: None,
                preserve_artifacts=preserve,
                restore_source_brief=restore,
                remove_active_pointer=lambda: None,
                invalidate_stale_run=lambda: None,
            )
            emit_transition_audit(run_home, journal, outcome="succeeded")
            publish()
            return ReturnEpicCommandResult(
                True, epic_id, request_id, eligibility=eligibility
            )


def holds_turn(work_id: str, *, root: Path) -> bool:
    home = locate_trunk(resolve_tracking_root(root)) / ".cascade" / "epic-returns"
    for path in home.glob("*/manifest.json"):
        manifest = json.loads(path.read_text())
        if manifest["state"] in {"returning", "returned"} and any(
            row["id"] == work_id for row in manifest["members"]
        ):
            return True
    return False


def recover_returns(*, root: Path) -> None:
    home = locate_trunk(resolve_tracking_root(root)) / ".cascade" / "epic-returns"
    for path in home.glob("*/manifest.json"):
        manifest = json.loads(path.read_text())
        if manifest["state"] == "returning":
            execute_return(path.parent.name, manifest["request_id"], root=root)


def reactivate_graph(epic_id: str, *, root: Path) -> None:
    """Restore the preserved graph into its retained owned integration trees."""
    from cascade.board.gitutil import commit_paths, has_git
    from cascade.board.store import _atomic_write_text
    from cascade.workspace.integration_worktree import get_integration_worktree
    from cascade.workspace.doc_root import read_doc_resolved

    home = return_home(root, epic_id)
    manifest = read_manifest(root, epic_id)
    if manifest is None or manifest["state"] != "returned":
        raise TransitionUnsafe("returned graph is unavailable")
    # A reviewed remote brief, when available, supersedes the preserved brief.
    epic = read_doc_resolved(epic_id, root=root)
    roots = {}
    epic_wt = get_integration_worktree(root, "epic", epic_id)
    epic_root = epic_wt.path if epic_wt else root
    for row in manifest["members"]:
        doc = epic if row["id"] == epic_id else parse_doc(home / row["backlog_path"])
        wt = get_integration_worktree(root, doc.meta.tier, doc.meta.id)
        destination_root = wt.path if wt else epic_root
        relative = Path(row["backlog_path"])
        if doc.meta.id == epic_id:
            relative = relative.parent.parent / "2_active" / relative.name
            doc.meta.status = "active"
        paths = roots.setdefault(destination_root, [])
        # Keep the prior contents in the immutable manifest/history before
        # removing duplicate lifecycle copies in this owned checkout.
        tier_home = destination_root / relative.parent.parent
        for column in ("1_backlog", "2_active", "3_completed"):
            for stale in (tier_home / column).glob(f"{doc.meta.id}_*.md"):
                if stale != destination_root / relative:
                    contents = stale.read_bytes()
                    digest = hashlib.sha256(contents).hexdigest()
                    _durable_write(
                        home / "restoration-history" / f"{doc.meta.id}-{digest}.md",
                        contents,
                    )
                    stale.unlink()
                    paths.append(stale)
        doc.meta.path = destination_root / relative
        if doc.meta.path.exists():
            contents = doc.meta.path.read_bytes()
            digest = hashlib.sha256(contents).hexdigest()
            _durable_write(
                home / "restoration-history" / f"{doc.meta.id}-{digest}.md", contents
            )
        _atomic_write_text(doc.meta.path, render_doc(doc))
        paths.append(doc.meta.path)
        row["live_root"] = str(destination_root)
    for checkout, paths in roots.items():
        if has_git(checkout):
            commit_paths(checkout, paths, f"docs: restore returned graph {epic_id}")
    manifest["state"] = "activated"
    _durable_write(home / "manifest.json", json.dumps(manifest).encode())
    invalidate_merged_board(root)
