"""Bounded candidate inventory and continuation coverage."""

from __future__ import annotations

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
    assert cursor


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

