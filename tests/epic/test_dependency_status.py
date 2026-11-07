"""Shared live dependency projection for War Room and planning agents."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cascade.board.store import list_board
from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    approve_dependency_installations,
)
from cascade.epic.dependency_bootstrap import (
    BootstrapEntryScope,
    BootstrapLimits,
    BootstrapScope,
    create_bootstrap,
)
from cascade.epic.dependency_evidence import (
    CheckOperationKind,
    CheckResult,
    admit_dependency_check,
    record_trusted_dependency_check_completion,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    write_dependency_manifest,
)
from cascade.epic.dependency_status import (
    dependency_status_chat_summary,
    project_dependency_status,
)
from cascade.war_room.serialize import board_view_from_index, work_meta_to_dict
from tests.support import add_doc, make_repo

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)


def _environment() -> EnvironmentIdentity:
    return EnvironmentIdentity(
        "local-container",
        "container",
        "linux",
        "x86_64",
        runner="podman",
        repository="cascade",
        worktree="/work/cascade",
        sandbox="container",
        runtime="python-3.12",
        container_digest="sha256:runner",
    )


def _entry(environment: EnvironmentIdentity, *, version: str = "1.2.3") -> DependencyEntry:
    return DependencyEntry(
        dependency_id="dep_tool",
        version=version,
        source=f"https://tool.example/{version}",
        digest=f"sha256:{version}",
        target_environment=environment,
        install_scope="project",
        install_destination=".tools/tool",
        operation=f"install tool {version} into .tools/tool",
        cleanup_plan="remove .tools/tool",
        verification_recipe=".tools/tool --version",
        expected_verification_result=f"tool {version}",
    )


def _board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    return root


def _write_manifest(root: Path, entry: DependencyEntry, revision: int = 0) -> None:
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(entry.target_environment, None, False, (entry,)),
        root=root,
        expected_revision=revision,
        recorded_at=NOW + timedelta(minutes=revision),
    )


def _scope(entry: DependencyEntry, revision: int = 1) -> BootstrapScope:
    return BootstrapScope(
        manifest_revision=revision,
        entries=(
            BootstrapEntryScope(
                dependency_id=entry.dependency_id,
                source=entry.source,
                integrity_reference=entry.integrity_reference or entry.digest,
                setup_operation=entry.operation,
                check_operation=entry.verification_recipe,
                paths=(entry.install_destination or entry.install_scope,),
                destination=entry.install_destination or entry.install_scope,
                cleanup=entry.cleanup_plan,
            ),
        ),
        feasibility_artifacts=(),
        limits=BootstrapLimits(30, 2, 4096),
    )


def test_blocked_projection_exposes_binding_guidance_and_missing_approval(tmp_path: Path) -> None:
    root = _board(tmp_path)
    entry = _entry(_environment())
    _write_manifest(root, entry)
    create_bootstrap("epic_001", _scope(entry), root=root, recorded_at=NOW)

    status = project_dependency_status("epic_001", root=root)
    row = status["dependencies"][0]

    assert status["status"] == "dependency_blocked"
    assert status["responsible_actor"] == "agent"
    assert row["binding"]["install_destination"] == ".tools/tool"
    assert row["bootstrap_scope"]["paths"] == [".tools/tool"]
    assert row["installation_approval"]["state"] == "missing"
    assert row["evidence"]["state"] == "missing_check"
    assert row["guidance"]["verification_operation"] == ".tools/tool --version"
    assert row["guidance"]["owned_artifact_cleanup"] == "remove .tools/tool"


def test_changed_binding_is_stale_while_attempt_mismatch_remains_visible(tmp_path: Path) -> None:
    root = _board(tmp_path)
    environment = _environment()
    original = _entry(environment)
    _write_manifest(root, original)
    create_bootstrap("epic_001", _scope(original), root=root, recorded_at=NOW)
    approve_dependency_installations(
        "epic_001",
        (original.dependency_id,),
        approver=AuthenticatedHuman("operator"),
        root=root,
        approved_at=NOW,
    )
    admission = admit_dependency_check(
        "epic_001",
        original.dependency_id,
        root=root,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=original.verification_recipe,
        admitted_at=NOW,
    )
    record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=root,
        actual_environment=environment,
        result=CheckResult.SUCCEEDED,
        redacted_output="tool 1.2.3",
        selected_version=original.version,
        integrity_reference=original.digest,
        completed_at=NOW + timedelta(seconds=1),
    )
    changed = replace(
        original,
        version="2.0.0",
        resolved_version="2.0.0",
        source="https://tool.example/2.0.0",
        digest="sha256:2.0.0",
        integrity_reference="sha256:2.0.0",
        operation="install tool 2.0.0 into .tools/tool",
    )
    _write_manifest(root, changed, revision=1)

    row = project_dependency_status("epic_001", root=root)["dependencies"][0]
    assert row["installation_approval"]["state"] == "stale"
    assert row["evidence"]["state"] == "stale_check"
    assert row["last_check"]["redacted_output"] == "tool 1.2.3"
    assert row["binding"]["version"] == "2.0.0"


def test_ready_projection_is_identical_in_board_and_chat_consumers(
    tmp_path: Path, monkeypatch
) -> None:
    class FixedClock:
        @staticmethod
        def now(tz):
            return NOW.astimezone(tz)

    monkeypatch.setattr("cascade.dependency_projection.datetime", FixedClock)
    root = _board(tmp_path)
    environment = _environment()
    entry = _entry(environment)
    _write_manifest(root, entry)
    create_bootstrap("epic_001", _scope(entry), root=root, recorded_at=NOW)
    admission = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=root,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=entry.verification_recipe,
        admitted_at=NOW,
    )
    record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=root,
        actual_environment=environment,
        result=CheckResult.SUCCEEDED,
        redacted_output="tool 1.2.3",
        selected_version=entry.version,
        integrity_reference=entry.digest,
        completed_at=NOW + timedelta(seconds=1),
    )

    projection = project_dependency_status("epic_001", root=root)
    meta = list_board(root).by_id["epic_001"]
    board_row = work_meta_to_dict(meta, root=root)

    assert projection["status"] == "ready"
    assert projection["dependencies"][0]["actual_environment"] == environment.to_dict()
    assert board_row["software_dependency_status"] == projection
    view = board_view_from_index(list_board(root), root=root)
    live_row = next(row for row in view["epics"]["2_active"] if row["id"] == "epic_001")
    assert live_row["software_dependency_status"] == projection
    assert live_row["dependency_status"]["outcome"] == "satisfied"
    assert '"status":"ready"' in dependency_status_chat_summary("epic_001", root=root)


def test_last_check_prefers_newer_in_progress_attempt_over_older_output(tmp_path: Path) -> None:
    root = _board(tmp_path)
    environment = _environment()
    entry = _entry(environment)
    _write_manifest(root, entry)
    create_bootstrap("epic_001", _scope(entry), root=root, recorded_at=NOW)
    completed = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=root,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=entry.verification_recipe,
        admitted_at=NOW,
    )
    record_trusted_dependency_check_completion(
        "epic_001",
        completed.attempt_id,
        root=root,
        actual_environment=environment,
        result=CheckResult.FAILED,
        redacted_output="old failure",
        selected_version=entry.version,
        integrity_reference=entry.digest,
        completed_at=NOW + timedelta(seconds=1),
    )
    current = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=root,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=entry.verification_recipe,
        admitted_at=NOW + timedelta(seconds=2),
    )

    last_check = project_dependency_status("epic_001", root=root)["dependencies"][0][
        "last_check"
    ]
    assert last_check["attempt_id"] == current.attempt_id
    assert last_check["result"] == "in_progress"
    assert last_check["redacted_output"] is None


def test_explicit_empty_manifest_is_ready_without_bootstrap_or_approvals(tmp_path: Path) -> None:
    root = _board(tmp_path)
    environment = _environment()
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment, None, True, ()),
        root=root,
        expected_revision=0,
        recorded_at=NOW,
    )

    projection = project_dependency_status("epic_001", root=root)
    assert projection["status"] == "ready"
    assert projection["explicit_no_dependencies"] is True
    assert projection["bootstrap"]["state"] == "not_required"
    assert projection["dependencies"] == []
