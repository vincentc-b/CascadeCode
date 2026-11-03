"""End-to-end durability and Git-safety contracts for Epic return."""

from __future__ import annotations

import subprocess
import threading

import pytest

from cascade.epic.lifecycle_gate import LifecycleGate
from cascade.epic.return_command import return_epic_to_backlog
from cascade.epic.return_eligibility import ReturnEligibilityInput, ReturnGraphMember
from cascade.epic.return_transaction import (
    ActiveToBacklogFiles,
    ActiveToBacklogTransaction,
    TransitionStep,
    TransitionUnsafe,
    execute_file_transaction,
    recover_file_transaction,
    transition_audit_path,
)


def _git(root, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _checkout(tmp_path):
    """Build a real clean integration worktree beneath an operator trunk."""

    trunk = tmp_path / "trunk"
    trunk.mkdir()
    _git(trunk, "init")
    _git(trunk, "config", "user.email", "tests@example.invalid")
    _git(trunk, "config", "user.name", "Transition tests")
    (trunk / "active.md").write_text("source brief\n", encoding="utf-8")
    (trunk / "active-pointer").write_text("active run\n", encoding="utf-8")
    _git(trunk, "add", ".")
    _git(trunk, "commit", "-m", "fixture")
    integration = trunk / ".cascade" / "worktrees" / "feat_epic_030"
    integration.parent.mkdir(parents=True)
    _git(trunk, "worktree", "add", "-b", "feat/epic-030-test", str(integration))
    return trunk, integration


def _files(root) -> ActiveToBacklogFiles:
    return ActiveToBacklogFiles(
        source_brief=root / "active.md",
        backlog_brief=root / "backlog.md",
        active_pointer=root / "active-pointer",
        preserved_artifact=root / "preserved" / "active.md",
        stale_run_marker=root / "stale-run",
    )


@pytest.mark.parametrize("boundary", tuple(TransitionStep))
def test_restart_after_every_durable_boundary_converges_in_a_real_worktree(
    tmp_path, monkeypatch, boundary: TransitionStep
) -> None:
    trunk, integration = _checkout(tmp_path)
    files = _files(integration)
    original_save = ActiveToBacklogTransaction._save

    def crash_after_boundary(self, journal):
        original_save(self, journal)
        if journal.completed_steps[-1] is boundary:
            raise RuntimeError(f"crash after {boundary.value}")

    with monkeypatch.context() as patch:
        patch.setattr(ActiveToBacklogTransaction, "_save", crash_after_boundary)
        with pytest.raises(RuntimeError, match=boundary.value):
            execute_file_transaction(
                root=integration, epic_id="epic_030", request_id="request-one", files=files
            )

    result = recover_file_transaction(
        root=integration, epic_id="epic_030", request_id="request-retry", files=files
    )

    assert result.recovered and result.state == "completed"
    assert result.journal is not None and result.journal.completed_steps == tuple(TransitionStep)
    assert files.preserved_artifact.read_text(encoding="utf-8") == "source brief\n"
    assert files.backlog_brief.read_text(encoding="utf-8") == "source brief\n"
    assert not files.active_pointer.exists()
    assert files.stale_run_marker.read_text(encoding="utf-8") == "invalidated\n"
    assert len(list((integration / ".cascade" / "epic-transition-audits").glob("*.json"))) == 1
    # The operator checkout is only ever used as the source of the worktree.
    assert (trunk / "active.md").read_text(encoding="utf-8") == "source brief\n"
    assert (trunk / "active-pointer").read_text(encoding="utf-8") == "active run\n"


def test_concurrent_public_requests_serialize_and_share_one_transition(tmp_path) -> None:
    _trunk, integration = _checkout(tmp_path)
    files = _files(integration)
    gate = LifecycleGate()
    first_entered = threading.Event()
    release_first = threading.Event()
    calls: list[str] = []
    results = []

    member = ReturnGraphMember(
        "epic_030", "epic", None, "source", "activation", True, False, True, True
    )
    snapshot = ReturnEligibilityInput(
        epic_id="epic_030", epic_tier="epic", epic_status="active",
        epic_transition_in_progress=False, graph=(member,), graph_complete=True,
        source_brief_revision="brief", lock_order=("epic_030",),
        conflicting_lifecycle_operation=False,
    )

    def transition(_epic_id: str, request_id: str) -> None:
        execute_file_transaction(
            root=integration, epic_id="epic_030", request_id=request_id, files=files
        )
        calls.append(request_id)
        if len(calls) == 1:
            first_entered.set()
            assert release_first.wait(1)

    def request(request_id: str) -> None:
        results.append(
            return_epic_to_backlog(
                "epic_030", request_id, actor="human", snapshot_loader=lambda _id: snapshot,
                transition=transition, gate=gate,
            )
        )

    first = threading.Thread(target=request, args=("first",))
    second = threading.Thread(target=request, args=("second",))
    first.start()
    assert first_entered.wait(1)
    second.start()
    assert len(calls) == 1
    release_first.set()
    first.join(1)
    second.join(1)

    assert len(results) == 2 and all(result.ok for result in results)
    journal = ActiveToBacklogTransaction(
        root=integration, epic_id="epic_030", request_id="ignored"
    ).load()
    assert journal is not None and journal.request_id == "first" and journal.complete
    assert transition_audit_path(integration, journal.transition_id).exists()
    assert len(list((integration / ".cascade" / "epic-transition-audits").glob("*.json"))) == 1


def test_git_safety_refuses_dirty_checkout_and_operator_trunk_without_mutation(tmp_path) -> None:
    trunk, integration = _checkout(tmp_path)
    integration_files = _files(integration)
    (integration / "unrelated.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(TransitionUnsafe, match="uncommitted changes"):
        execute_file_transaction(
            root=integration, epic_id="epic_030", request_id="dirty", files=integration_files
        )
    assert not (integration / ".cascade" / "epic-transitions").exists()

    trunk_files = _files(trunk)
    with pytest.raises(TransitionUnsafe, match="operator trunk"):
        execute_file_transaction(
            root=trunk, epic_id="epic_030", request_id="trunk", files=trunk_files
        )
    assert (trunk / "active.md").read_text(encoding="utf-8") == "source brief\n"
    assert (trunk / "active-pointer").read_text(encoding="utf-8") == "active run\n"
    assert not (trunk / ".cascade" / "epic-transitions").exists()
