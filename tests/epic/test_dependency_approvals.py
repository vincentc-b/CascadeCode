"""Integration coverage for per-dependency installation authority."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    DependencyApprovalError,
    InstallationApprovalDenied,
    approve_dependency_installations,
    current_installation_approval,
    invoke_approved_installation,
    read_installation_approvals,
    require_installation_approval,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    InstallationBinding,
    read_dependency_manifest,
    write_dependency_manifest,
)
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    return root


@pytest.fixture
def target() -> EnvironmentIdentity:
    return EnvironmentIdentity(
        "ci-linux",
        "container",
        "linux",
        "x86_64",
        runner="github-actions",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="container",
        runtime="python-3.12",
        container_digest="sha256:runner-image",
    )


def dependency(
    target: EnvironmentIdentity,
    dependency_id: str = "dep_python",
) -> DependencyEntry:
    return DependencyEntry(
        dependency_id=dependency_id,
        version="3.12.7",
        source="https://python.example/releases/3.12.7",
        digest="sha256:abc123",
        target_environment=target,
        install_scope="epic worktree at .tools/python",
        operation="install Python 3.12.7 into .tools/python",
        cleanup_plan="remove .tools/python",
        verification_recipe=".tools/python/bin/python --version",
    )


def write_entries(
    board: Path,
    target: EnvironmentIdentity,
    entries: tuple[DependencyEntry, ...],
    *,
    expected_revision: int,
) -> None:
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, False, entries),
        root=board,
        expected_revision=expected_revision,
    )


def approve(board: Path, dependency_ids: tuple[str, ...] = ("dep_python",)):
    return approve_dependency_installations(
        "epic_001",
        dependency_ids,
        approver=AuthenticatedHuman("human-42@example.test"),
        root=board,
        approved_at=datetime(2026, 11, 7, 12, 30, tzinfo=timezone.utc),
    )


def test_batch_persists_independent_human_approvals_and_reloads(
    board: Path, target: EnvironmentIdentity
) -> None:
    python = dependency(target)
    node = replace(
        dependency(target, "dep_node"),
        version="22.11.0",
        source="https://node.example/v22.11.0",
        digest="sha256:def456",
        operation="install Node 22.11.0 into .tools/node",
        install_scope="epic worktree at .tools/node",
        cleanup_plan="remove .tools/node",
    )
    write_entries(board, target, (python, node), expected_revision=0)

    created = approve(board, ("dep_python", "dep_node"))
    reloaded = read_installation_approvals("epic_001", root=board)

    assert reloaded == created
    assert len({row.approval_id for row in created}) == 2
    assert {row.binding.dependency_id for row in created} == {"dep_python", "dep_node"}
    assert all(row.approver_id == "human-42@example.test" for row in created)
    assert all(
        row.approved_at == datetime(2026, 11, 7, 12, 30, tzinfo=timezone.utc)
        for row in created
    )
    assert all(row.reviewed_manifest_revision == 1 for row in created)
    assert tuple(row.reviewed_entry for row in created) == (python, node)

    # One changed entry loses authority; a manifest revision and a verification-only
    # edit leave the other entry's independently bound approval current.
    changed_python = replace(python, digest="sha256:new-python")
    changed_node = replace(node, verification_recipe="node --version && npm --version")
    write_entries(board, target, (changed_python, changed_node), expected_revision=1)
    assert (
        current_installation_approval(
            "epic_001", "dep_python", created[0].approval_id, root=board
        )
        is None
    )
    assert (
        current_installation_approval(
            "epic_001", "dep_node", created[1].approval_id, root=board
        )
        == created[1]
    )


def test_reviewed_batch_rejects_one_stale_binding_without_writing_any_approval(
    board: Path, target: EnvironmentIdentity
) -> None:
    python = dependency(target)
    node = replace(
        dependency(target, "dep_node"),
        version="22.11.0",
        source="https://node.example/v22.11.0",
        digest="sha256:def456",
        operation="install Node 22.11.0 into .tools/node",
        install_scope="epic worktree at .tools/node",
        cleanup_plan="remove .tools/node",
    )
    write_entries(board, target, (python, node), expected_revision=0)
    reviewed = {
        row.dependency_id: InstallationBinding.from_entry(row)
        for row in (python, node)
    }
    changed_python = replace(python, digest="sha256:changed")
    write_entries(board, target, (changed_python, node), expected_revision=1)

    with pytest.raises(DependencyApprovalError, match="binding is stale"):
        approve_dependency_installations(
            "epic_001",
            ("dep_python", "dep_node"),
            approver=AuthenticatedHuman("human-42@example.test"),
            root=board,
            expected_manifest_revision=2,
            expected_bindings=reviewed,
        )

    assert read_installation_approvals("epic_001", root=board) == ()


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("dependency_id", "dep_changed"),
        ("version", "3.12.8"),
        ("source", "https://mirror.example/python-3.12.7"),
        ("digest", "sha256:changed"),
        (
            "target_environment",
            EnvironmentIdentity("ci-arm", "container", "linux", "aarch64"),
        ),
        ("install_scope", "system destination /opt/python"),
        ("operation", "upgrade Python to 3.12.7"),
        ("cleanup_plan", "restore the previous toolchain"),
    ),
)
def test_every_binding_field_invalidates_only_that_entry(
    board: Path,
    target: EnvironmentIdentity,
    field: str,
    changed: object,
) -> None:
    original = dependency(target)
    write_entries(board, target, (original,), expected_revision=0)
    approval = approve(board)[0]
    revised = replace(original, **{field: changed})
    manifest_target = revised.target_environment
    write_entries(board, manifest_target, (revised,), expected_revision=1)

    assert (
        current_installation_approval(
            "epic_001", original.dependency_id, approval.approval_id, root=board
        )
        is None
    )


@pytest.mark.parametrize("field", ("version", "source", "digest"))
def test_unknown_exact_authority_data_blocks_the_entire_batch(
    board: Path,
    target: EnvironmentIdentity,
    field: str,
) -> None:
    exact = dependency(target)
    unknown = replace(dependency(target, "dep_unknown"), **{field: "unknown"})
    write_entries(board, target, (exact, unknown), expected_revision=0)

    with pytest.raises(DependencyApprovalError, match=f"unknown exact {field}"):
        approve(board, ("dep_python", "dep_unknown"))
    assert read_installation_approvals("epic_001", root=board) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("version", "latest"),
        ("source", "https://packages.example/tool/latest/archive"),
        ("digest", "sha256:latest"),
    ),
)
def test_latest_references_cannot_be_approved(
    board: Path,
    target: EnvironmentIdentity,
    field: str,
    value: str,
) -> None:
    write_entries(
        board,
        target,
        (replace(dependency(target), **{field: value}),),
        expected_revision=0,
    )

    with pytest.raises(DependencyApprovalError, match=f"unknown exact {field}"):
        approve(board)


def test_operation_boundary_denies_before_mutation_even_with_execution_capability(
    board: Path, target: EnvironmentIdentity
) -> None:
    entry = dependency(target)
    write_entries(board, target, (entry,), expected_revision=0)
    mutated: list[str] = []

    # These capabilities intentionally do not enter the approval API.  They can
    # permit execution, but cannot confer installation authority.
    provider_mode = "yolo"
    worktree_context = "owned"
    assert (provider_mode, worktree_context) == ("yolo", "owned")
    with pytest.raises(InstallationApprovalDenied, match="requires an approval ID"):
        invoke_approved_installation(
            "epic_001",
            "dep_python",
            None,
            InstallationBinding.from_entry(entry),
            lambda: mutated.append("installed"),
            root=board,
        )
    assert mutated == []

    approval = approve(board)[0]
    with pytest.raises(InstallationApprovalDenied, match="does not match"):
        invoke_approved_installation(
            "epic_001",
            "dep_python",
            approval.approval_id,
            replace(approval.binding, operation="upgrade Python behind the approval's back"),
            lambda: mutated.append("installed"),
            root=board,
        )
    assert mutated == []
    assert (
        invoke_approved_installation(
            "epic_001",
            "dep_python",
            approval.approval_id,
            InstallationBinding.from_entry(entry),
            lambda: "installed",
            root=board,
        )
        == "installed"
    )


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("dependency_id", "dep_other"),
        ("version", "3.12.8"),
        ("source", "https://mirror.example/python"),
        ("digest", "sha256:other"),
        ("target_environment", EnvironmentIdentity(
            "other", "container", "linux", "x86_64",
            runner="other", repository="example/cascade", worktree="/work/cascade",
            sandbox="container", runtime="python-3.12",
            container_digest="sha256:runner-image",
        )),
        ("install_scope", "system"),
        ("install_destination", "/opt/python"),
        ("operation", "upgrade Python"),
        ("cleanup_plan", "leave files behind"),
    ),
)
def test_operation_boundary_compares_complete_attempted_binding(
    board: Path,
    target: EnvironmentIdentity,
    field: str,
    changed: object,
) -> None:
    entry = dependency(target)
    write_entries(board, target, (entry,), expected_revision=0)
    approval = approve(board)[0]
    mutated: list[str] = []

    with pytest.raises(InstallationApprovalDenied, match="binding does not match"):
        invoke_approved_installation(
            "epic_001",
            "dep_python",
            approval.approval_id,
            replace(approval.binding, **{field: changed}),
            lambda: mutated.append("installed"),
            root=board,
        )
    assert mutated == []


def test_read_only_manifest_check_needs_no_installation_approval(
    board: Path, target: EnvironmentIdentity
) -> None:
    entry = dependency(target)
    write_entries(board, target, (entry,), expected_revision=0)

    # Discovery/validation remains its normal public read path.  Only setup
    # mutation callers cross require_installation_approval.
    assert read_dependency_manifest("epic_001", root=board).dependencies == (entry,)
    with pytest.raises(InstallationApprovalDenied):
        require_installation_approval(
            "epic_001", "dep_python", None, InstallationBinding.from_entry(entry), root=board
        )


def test_only_an_authenticated_human_can_mint_authority(
    board: Path, target: EnvironmentIdentity
) -> None:
    write_entries(board, target, (dependency(target),), expected_revision=0)

    with pytest.raises(DependencyApprovalError, match="authenticated human"):
        approve_dependency_installations(  # type: ignore[arg-type]
            "epic_001", ("dep_python",), approver="plan-approved", root=board
        )
    assert read_installation_approvals("epic_001", root=board) == ()
