from __future__ import annotations

import subprocess
from pathlib import Path

from cascade.feature.audit_recovery import (
    resume_planning_owner,
    retry_owned_publication,
)
from cascade.task.action_recovery import create_or_load_action
from cascade.watchdog.audit import project_audit_observation
from cascade.workspace.integration_worktree import (
    IntegrationWorktree,
    save_registry,
)
from tests.support import add_doc, make_repo


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _feature_repo(tmp_path: Path) -> tuple[Path, Path]:
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
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "feature board")
    checkout = root / ".cascade" / "worktrees" / "feat_feat_001"
    checkout.parent.mkdir(parents=True)
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "worktree", "add", "-b", "feat/feat_001", str(checkout), base)
    save_registry(
        root,
        [
            IntegrationWorktree(
                "feature", "feat_001", "feat/feat_001", checkout, base
            )
        ],
    )
    return root, checkout


def test_owner_adapter_requires_resumable_graph_and_protects_dirty_worktree(
    tmp_path: Path,
) -> None:
    root, checkout = _feature_repo(tmp_path)
    initial = project_audit_observation(
        "feat_001", root=root, monotonic=lambda: 0.0
    )

    no_input = resume_planning_owner(
        "feat_001", generation=initial.generation.value, root=root
    )
    assert no_input["state"] == "refused"
    assert no_input["reason"] == "no_resumable_graph_input"

    (checkout / "uncommitted.txt").write_text("keep me", encoding="utf-8")
    dirty = resume_planning_owner(
        "feat_001", generation=initial.generation.value, root=root
    )
    assert dirty["state"] == "refused"
    assert dirty["reason"] == "dirty_feature_worktree"
    assert (checkout / "uncommitted.txt").read_text(encoding="utf-8") == "keep me"


def test_owned_publication_retry_preserves_original_action_identity(
    tmp_path: Path, monkeypatch
) -> None:
    root, _checkout = _feature_repo(tmp_path)
    action_id = "feat_001:integration_branch_update"
    create_or_load_action(
        action_id,
        "integration_branch_update",
        root=root,
        attempt_bound=3,
        recovery_state="retryable",
        failure_classification="transient_retry",
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "feat_001"},
    )
    observation = project_audit_observation("feat_001", root=root)
    received: list[str] = []

    def retry(received_action_id: str, **_kwargs):
        received.append(received_action_id)
        return {
            "action_id": received_action_id,
            "recovery_state": "completed",
        }

    monkeypatch.setattr(
        "cascade.feature.branch_recovery.retry_integration_branch_update", retry
    )
    result = retry_owned_publication(
        action_id,
        feature_id="feat_001",
        generation=observation.generation.value,
        root=root,
    )

    assert received == [action_id]
    assert result["ok"] is True
    assert result["state"] == "reconciled"
    assert result["result_id"] == action_id
