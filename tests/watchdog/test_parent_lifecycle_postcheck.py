import json
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.watchdog.incident_postcheck import reconcile_parent_lifecycle_incident
from cascade.watchdog.incidents import incident_record
from cascade.watchdog.reservations import verify_incident_postcheck


GENERATION = "sha256:" + "4" * 64
STAMP = datetime(2026, 11, 24, tzinfo=timezone.utc)


def _contract(*, outcome: str = "deferred") -> dict:
    value = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="parent_lifecycle_mismatch",
        generation=GENERATION,
        evidence={
            "feature_id": "feat_001",
            "reason": "unresolved_recovery_reference",
            "parent_lifecycle_evidence": {
                "parent": {"epic_id": "epic_001"},
                "tested_heads": {
                    "validation": {
                        "task_id": "task_001",
                        "deliverable_sha": "source",
                        "feature_base_sha": "target",
                    }
                },
            },
        },
        selected_capability="feature_repair",
        result={
            "adapter_result": {
                "action_id": "feature_repair:feat_001:one",
                "generation": 2,
                "phase": "retirement_pending",
                "executed": True,
            }
        },
        outcome=outcome,  # type: ignore[arg-type]
        now=STAMP,
    )
    return value


def _write_incident(root: Path, incident: dict) -> None:
    path = root / ".cascade" / "executions.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 3,
                "actions": {
                    "reservation": {
                        "action_id": "reservation",
                        "recovery_state": "retryable",
                        "incident": incident,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_exact_postcheck_is_the_only_path_to_verified_history(tmp_path: Path) -> None:
    _write_incident(tmp_path, _contract())

    assert verify_incident_postcheck(
        "task_001",
        "parent_lifecycle_mismatch",
        GENERATION,
        {
            "verified": True,
            "verified_at": STAMP.isoformat(),
            "reason": "all_generation_obligations_proven",
        },
        root=tmp_path,
        now=STAMP,
    )

    payload = json.loads((tmp_path / ".cascade" / "executions.json").read_text())
    row = payload["actions"]["reservation"]
    assert row["incident"]["outcome"] == "success"
    assert row["incident"]["result"]["postcheck"]["verified"] is True
    assert [receipt["stage"] for receipt in row["incident"]["stage_receipts"]] == [
        "verifying",
        "resolved",
    ]
    assert row["incident"]["stage_receipts"][-1]["verification_reference"] == GENERATION
    assert row["incident_history"][-1]["outcome"] == "deferred"
    assert row["recovery_state"] == "completed"
    assert not verify_incident_postcheck(
        "task_001",
        "parent_lifecycle_mismatch",
        "sha256:" + "5" * 64,
        {"verified": True},
        root=tmp_path,
    )


def test_repeated_and_restarted_postcheck_does_not_reexecute_same_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.watchdog.audit_recovery import AuditRecoveryWorker

    calls: list[str] = []
    monkeypatch.setattr(
        "cascade.watchdog.incident_postcheck.reconcile_parent_lifecycle_incident",
        lambda *_args, **_kwargs: {"verified": False, "reason": "review_pending"},
    )
    monkeypatch.setattr(
        "cascade.watchdog.audit_recovery.dispatch_audit_recovery",
        lambda *_args, **_kwargs: calls.append("executed") or True,
    )
    request = (
        {
            "work_id": "task_001",
            "authoritative_generation": GENERATION,
            "postcheck_generation": GENERATION,
            "failure_class": "parent_lifecycle_mismatch",
        },
    )
    for _restart in range(2):
        worker = AuditRecoveryWorker(tmp_path)
        worker.submit(request)
        worker._pending.join()
        worker.stop(timeout=2)

    assert calls == []


@pytest.mark.parametrize(
    ("changed", "reason"),
    [
        ("none", "all_generation_obligations_proven"),
        ("review", "pending:review_generation_accepted"),
        ("runtime", "pending:loaded_runtime_current"),
        ("lease", "pending:execution_lease_retired"),
        ("feature_worktree", "pending:feature_worktree_retired"),
    ],
)
def test_postcheck_fails_closed_when_a_relevant_fact_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
    reason: str,
) -> None:
    import cascade.watchdog.incident_postcheck as subject

    incident = _contract()
    monkeypatch.setattr(subject, "_incident", lambda *_args: incident)
    monkeypatch.setattr(
        subject, "verify_incident_postcheck", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(subject, "task_lifecycle_lock", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(
        subject,
        "load_action",
        lambda *_args, **_kwargs: {
            "recovery_state": "completed",
            "metadata": {
                "final_validation": incident["evidence"]["parent_lifecycle_evidence"][
                    "tested_heads"
                ]["validation"]
            },
        },
    )

    def completed(work_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=work_id,
            status="completed",
            path=tmp_path / "docs" / "tasks" / "3_completed" / f"{work_id}.md",
        )

    board = SimpleNamespace(
        by_id={"task_001": completed("task_001"), "feat_001": completed("feat_001")}
    )
    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.merged_board", lambda *_args: board
    )
    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.resolve_mutation_owner",
        lambda *_args, **_kwargs: tmp_path,
    )
    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.get_integration_worktree",
        lambda _root, kind, _work_id: (
            object() if changed == "feature_worktree" and kind == "feature" else None
        ),
    )
    monkeypatch.setattr(
        "cascade.feature.repair.feature_repair_actions",
        lambda *_args, **_kwargs: [
            {
                "action_id": "feature_repair:feat_001:one",
                "generation": 2,
                "phase": "verified",
            }
        ],
    )
    monkeypatch.setattr(
        "cascade.review.review_record_for_feature",
        lambda *_args, **_kwargs: {
            "current_generation": 3 if changed == "review" else 2,
            "generation": 2,
            "closed": True,
            "reconciliation_status": "accepted",
            "source_head": "source",
            "target_head": "target",
            "accepted_source_head": "source",
            "accepted_target_head": "target",
            "accepted_merge_sha": "merge",
        },
    )
    monkeypatch.setattr(
        "cascade.task.execution.execution_lease_is_live",
        lambda *_args, **_kwargs: changed == "lease",
    )
    monkeypatch.setattr(
        "cascade.workspace.supervisor_status.read_supervisor_status",
        lambda *_args, **_kwargs: {
            "runtime_identity": {"authority_manifest_id": "authority"}
        },
    )
    monkeypatch.setattr(
        "cascade.workspace.runtime_identity.verify_current_loaded_runtime_identity",
        lambda *_args, **_kwargs: {
            "state": "refused" if changed == "runtime" else "current",
            "reason": "stale process" if changed == "runtime" else None,
            "identity": None,
        },
    )

    result = reconcile_parent_lifecycle_incident(
        "task_001", GENERATION, root=tmp_path, now=STAMP
    )

    assert result["verified"] is (changed == "none")
    assert result["reason"] == reason
