"""Bounded candidate inventory and continuation coverage."""

from __future__ import annotations

import base64
import json
import subprocess
from datetime import date
from pathlib import Path

import cascade.watchdog.audit as audit
from cascade.board.context import set_project_context
from cascade.watchdog.audit import CandidateBudget, select_audit_candidates
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo


def _commit(root: Path, message: str = "snapshot") -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", message], cwd=root, check=True
    )


def _ids(page: object) -> list[str]:
    return [str(row.work_id) for row in page.candidates]  # type: ignore[attr-defined]


def test_cursor_is_bounded_fair_and_eventually_covers_old_unresolved_work(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    add_doc(
        root,
        id="task_002",
        title="Old completed task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    _commit(root)
    sidecars = root / ".cascade"
    sidecars.mkdir(exist_ok=True)
    (sidecars / "executions.json").write_text(
        json.dumps(
            {
                "actions": {
                    "repair-old": {
                        "action_id": "repair-old",
                        "affected_work_id": "task_002",
                        "recovery_state": "retryable",
                    },
                    "finished": {
                        "action_id": "finished",
                        "affected_work_id": "task_003",
                        "recovery_state": "completed",
                        "recovery": {
                            "evidence": {"affected_work_id": "task_003"}
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    # A second source names the same typed identity; it must not duplicate it.
    (sidecars / "reviews.json").write_text(
        json.dumps({"task_002": {"state": "open"}}), encoding="utf-8"
    )
    (sidecars / "worktrees.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "kind": "task",
                        "work_id": "task_002",
                        "branch": "task/task_002",
                        "path": ".cascade/worktrees/task_task_002",
                        "base_sha": "a" * 40,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cursor = None
    seen: list[str] = []
    pages = []
    for _ in range(3):
        page = select_audit_candidates(
            cursor,
            CandidateBudget(max_items=2),
            root=root,
            today=date(2026, 11, 20),
        )
        pages.append(page)
        seen.extend(_ids(page))
        cursor = page.next_cursor

    assert all(len(page.candidates) <= 2 for page in pages)
    assert {"task_001", "task_002", "feat_001", "epic_001"} <= set(seen)
    assert seen.count("task_002") == 1
    assert "task_003" not in seen
    old = next(row for page in pages for row in page.candidates if str(row.work_id) == "task_002")
    assert old.reasons == (
        "unresolved_action",
        "unresolved_cleanup",
        "unresolved_review",
    )
    assert old.evidence_errors == ("registered_worktree_unavailable",)
    assert len(old.source_references) >= 2
    assert cursor


def test_both_pools_reserve_every_fourth_admission_for_history(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_001", title="Feature", tier="feature",
        status="active", parent="epic_001",
    )
    for index in range(1, 6):
        add_doc(
            root, id=f"task_{index:03d}", title=f"Current {index}", tier="task",
            status="active", parent="feat_001",
        )
    add_doc(
        root, id="task_900", title="Historical", tier="task",
        status="completed", parent="feat_001",
    )
    _commit(root)
    (root / ".cascade" / "executions.json").write_text(
        json.dumps({
            "actions": {
                "old": {
                    "affected_work_id": "task_900",
                    "recovery_state": "retryable",
                }
            }
        }),
        encoding="utf-8",
    )

    page = select_audit_candidates(
        budget=CandidateBudget(max_items=4), root=root, today=date(2099, 1, 1)
    )

    assert _ids(page)[:3] == ["task_001", "feat_001", "epic_001"]
    assert _ids(page)[3] == "task_900"
    assert len(set(_ids(page))) == 4
    assert page.deferred


def test_version_one_cursor_migrates_to_independent_pool_positions() -> None:
    payload = {
        "v": 1,
        "after": {"task": "task_009", "feature": None, "epic": "epic_002"},
        "next_tier": 1,
    }
    cursor = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")

    states, admitted = audit._decode_candidate_cursor(cursor)

    assert admitted == 0
    assert states["ongoing"] == states["historical"]
    assert states["ongoing"]["after"]["task"] == "task_009"
    assert states["ongoing"]["next_tier"] == 1


def test_split_repository_projection_uses_tracking_docs_and_product_worktrees(
    tmp_path: Path,
) -> None:
    product = make_repo(tmp_path / "product")
    tracking = make_repo(tmp_path / "tracking")
    add_doc(tracking, id="epic_001", title="Epic", tier="epic", status="active")
    _commit(product, "product")
    _commit(tracking, "tracking")
    worktree = product / ".cascade" / "worktrees" / "epic_epic_001"
    worktree.mkdir(parents=True)
    (product / ".cascade" / "worktrees.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "kind": "epic",
                        "work_id": "epic_001",
                        "branch": "epic/epic_001",
                        "path": ".cascade/worktrees/epic_epic_001",
                        "base_sha": "a" * 40,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    set_project_context(ProjectContext.split(product, tracking))
    try:
        page = select_audit_candidates(root=product)
    finally:
        set_project_context(None)

    assert _ids(page) == ["epic_001"]
    candidate = page.candidates[0]
    assert candidate.tracking_repository == tracking.resolve()
    assert candidate.product_repository == product.resolve()
    assert candidate.registered_worktree == worktree.resolve()


def test_unreadable_sources_and_missing_canonical_documents_are_unavailable(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    _commit(root)
    sidecars = root / ".cascade"
    sidecars.mkdir(exist_ok=True)
    (sidecars / "reviews.json").write_text("{broken", encoding="utf-8")
    (sidecars / "executions.json").write_text(
        json.dumps(
            {
                "actions": {
                    "lost": {
                        "affected_work_id": "task_999",
                        "recovery_state": "failed",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    before = (sidecars / "executions.json").read_bytes()
    (sidecars / "worktrees.lock").unlink(missing_ok=True)

    page = select_audit_candidates(root=root)

    assert "review:unavailable" in page.unavailable_evidence
    missing = next(row for row in page.candidates if str(row.work_id) == "task_999")
    assert not missing.evidence_available
    assert missing.evidence_errors == ("canonical_document_unavailable",)
    assert (sidecars / "executions.json").read_bytes() == before
    assert not (sidecars / "worktrees.lock").exists()


def test_malformed_named_document_remains_a_retryable_candidate(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_001", title="Feature", tier="feature",
        status="active", parent="epic_001",
    )
    malformed = root / "docs" / "tasks" / "2_active" / "task_777_broken.md"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text("---\nid: [not valid\n---\n", encoding="utf-8")
    _commit(root)

    page = select_audit_candidates(root=root)
    candidate = next(row for row in page.candidates if str(row.work_id) == "task_777")

    assert candidate.reasons == ("malformed_document",)
    assert candidate.evidence_errors == ("malformed_document",)
    assert not candidate.evidence_available


def test_unchanged_passes_reuse_completed_inventory_and_new_completion_is_seen(
    tmp_path: Path, monkeypatch,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Old", tier="epic", status="completed")
    _commit(root)
    scanned: list[Path] = []
    original = audit._scan_meta

    def counting_scan(path: Path):
        scanned.append(path)
        return original(path)

    monkeypatch.setattr(audit, "_scan_meta", counting_scan)
    select_audit_candidates(root=root, today=date(2026, 11, 20))
    scanned.clear()
    select_audit_candidates(root=root, today=date(2026, 11, 20))
    assert scanned
    assert all("3_completed" not in path.parts for path in scanned)

    add_doc(root, id="epic_003", title="Recent", tier="epic", status="completed")
    page = select_audit_candidates(root=root, today=date.today())
    assert "epic_003" in _ids(page)
    assert any("3_completed" in path.parts for path in scanned)


def test_owned_worktree_inventory_uses_canonical_status_and_discovers_unstarted_children(tmp_path, monkeypatch):
    from cascade.board.store import move_doc
    from cascade.workspace.integration_worktree import (
        IntegrationWorktree, merged_board_readonly, save_registry,
    )

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _commit(root)
    path = root / ".cascade/worktrees/feat_feat_001"
    subprocess.run(["git", "worktree", "add", "-b", "feat/feat_001", str(path)], cwd=root, check=True, capture_output=True)
    move_doc("feat_001", "active", root=path)
    add_doc(path, id="task_001", title="Unstarted", tier="task", parent="feat_001")
    add_doc(path, id="task_002", title="Delivered", tier="task", parent="feat_001", status="completed")
    _commit(path)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    save_registry(root, [IntegrationWorktree("feature", "feat_001", "feat/feat_001", path, sha)])
    (root / ".cascade/worktrees.lock").unlink()
    board = merged_board_readonly(root)
    page = select_audit_candidates(root=root)
    rows = {str(row.work_id): row for row in page.candidates}

    assert set(rows) == set(board.by_id)
    assert all(row.evidence_available for row in rows.values())
    assert "nonterminal" in rows["feat_001"].reasons
    assert "nonterminal" in rows["task_001"].reasons
    assert "recently_completed" in rows["task_002"].reasons
    assert not (root / ".cascade/worktrees.lock").exists()
    # Pagination remains fair after worktree-only rows enter the inventory.
    cursor = None
    found = set()
    for _ in range(4):
        page = select_audit_candidates(cursor, CandidateBudget(max_items=1), root=root)
        assert len(page.candidates) == 1
        found.update(_ids(page))
        cursor = page.next_cursor
    assert found == set(rows)
    scanned = []
    original = audit._scan_meta

    def record_scan(path):
        scanned.append(path)
        return original(path)

    monkeypatch.setattr(audit, "_scan_meta", record_scan)
    select_audit_candidates(root=root)
    assert all("3_completed" not in path.parts for path in scanned)
    # Retained worktrees cannot resurrect an Epic accepted on trunk.
    move_doc("epic_001", "completed", root=root)
    page = select_audit_candidates(root=root)
    epic = next(row for row in page.candidates if str(row.work_id) == "epic_001")
    assert "nonterminal" not in epic.reasons
    assert merged_board_readonly(root).by_id["epic_001"].status == "completed"


def test_split_inventory_reads_tracking_worktree_and_tracking_recovery_store(tmp_path):
    from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
    from cascade.task.action_recovery import create_or_load_action

    product = make_repo(tmp_path / "product")
    tracking = make_repo(tmp_path / "tracking")
    add_doc(tracking, id="epic_001", title="Epic", tier="epic", status="active")
    _commit(tracking)
    path = tracking / ".cascade/worktrees/feat_feat_001"
    subprocess.run(["git", "worktree", "add", "-b", "feat/feat_001", str(path)], cwd=tracking, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tracking, text=True).strip()
    save_registry(tracking, [IntegrationWorktree("feature", "feat_001", "feat/feat_001", path, sha)])
    add_doc(path, id="feat_001", title="Feature", tier="feature", parent="epic_001", status="active")
    add_doc(path, id="task_001", title="Delivered", tier="task", parent="feat_001", status="completed")
    _commit(path)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tracking, text=True).strip()
    save_registry(tracking, [IntegrationWorktree("feature", "feat_001", "feat/feat_001", path, sha)])
    # Product plan copies must never become authoritative lifecycle inventory.
    add_doc(product, id="epic_001", title="Stale Epic", tier="epic", status="active")
    add_doc(product, id="feat_001", title="Stale Feature", tier="feature", parent="epic_001", status="active")
    add_doc(product, id="task_999", title="Stale product copy", tier="task", parent="feat_001")
    set_project_context(ProjectContext.split(product, tracking))
    try:
        create_or_load_action("task_001:repair", "queued_task_merge", root=product,
                              evidence={"affected_work_id": "task_001"}, recovery_state="retryable", attempt_bound=3)
        page = select_audit_candidates(root=product, today=date(2099, 1, 1))
    finally:
        set_project_context(None)
    rows = {str(row.work_id): row for row in page.candidates}
    assert set(rows) == {"epic_001", "feat_001", "task_001"}
    assert rows["task_001"].evidence_available
    assert "unresolved_action" in rows["task_001"].reasons
    assert "task_999" not in rows
    assert not (product / ".cascade/executions.json").exists()

