"""Public persistence and validation contracts for epic dependency manifests."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    DependencyManifestNotFound,
    EnvironmentIdentity,
    InstallationApproval,
    InstallationBinding,
    InvalidDependencyManifest,
    StaleDependencyManifestRevision,
    environment_identities_match,
    installation_approval_is_valid,
    read_dependency_manifest,
    read_dependency_manifest_history,
    require_dependency_manifest,
    validate_dependency_manifest,
    write_dependency_manifest,
)
from cascade.workspace import prepare_up
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    return root


@pytest.fixture
def target() -> EnvironmentIdentity:
    return EnvironmentIdentity(
        environment_id="ci-linux-x86_64",
        kind="container",
        platform="linux",
        architecture="x86_64",
        runner="github-actions",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="container",
        runtime="python-3.12",
        container_digest="sha256:runner-image",
    )


def dependency(target: EnvironmentIdentity) -> DependencyEntry:
    return DependencyEntry(
        dependency_id="dep_python",
        version="3.12.7",
        source="https://python.example/releases/3.12.7",
        digest="sha256:abc123",
        target_environment=target,
        install_scope="project toolchain",
        operation="install Python 3.12.7",
        cleanup_plan="remove the project toolchain directory",
        verification_recipe="python --version",
    )


def test_absent_manifest_is_distinct_and_required_reads_fail_closed(
    board: Path,
) -> None:
    assert read_dependency_manifest("epic_001", root=board) is None
    assert read_dependency_manifest_history("epic_001", root=board) == ()

    with pytest.raises(DependencyManifestNotFound, match="next planning action"):
        require_dependency_manifest("epic_001", root=board)


def test_empty_manifest_requires_explicit_none_required(
    board: Path, target: EnvironmentIdentity
) -> None:
    with pytest.raises(InvalidDependencyManifest, match="explicitly set none_required"):
        validate_dependency_manifest(
            {
                "target_environment": target.to_dict(),
                "actual_environment": None,
                "none_required": False,
                "dependencies": [],
            }
        )

    stored = write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, True, ()),
        root=board,
        expected_revision=0,
        recorded_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
    )

    assert stored.revision == 1
    assert stored.none_required is True
    assert stored.dependencies == ()
    assert require_dependency_manifest("epic_001", root=board) == stored


def test_revisions_are_append_only_addressable_and_optimistically_guarded(
    board: Path, target: EnvironmentIdentity
) -> None:
    first = write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, False, (dependency(target),)),
        root=board,
        expected_revision=0,
    )
    revised_entry = replace(
        dependency(target), version="3.12.8", digest="sha256:def456"
    )
    second = write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, target, False, (revised_entry,)),
        root=board,
        expected_revision=1,
    )

    assert first.revision == 1
    assert second.revision == 2
    assert read_dependency_manifest("epic_001", root=board) == second
    assert read_dependency_manifest("epic_001", root=board, revision=1) == first
    assert read_dependency_manifest_history("epic_001", root=board) == (first, second)
    assert (
        write_dependency_manifest(
            "epic_001", second.draft, root=board, expected_revision=2
        )
        == second
    )

    with pytest.raises(StaleDependencyManifestRevision, match="current is 2"):
        write_dependency_manifest(
            "epic_001", first.draft, root=board, expected_revision=1
        )


def test_environment_and_installation_approval_bindings_are_exact(
    target: EnvironmentIdentity,
) -> None:
    entry = dependency(target)
    approval = InstallationApproval(
        approval_id="approval-1",
        binding=InstallationBinding.from_entry(entry),
        approver_id="human@example.test",
        approved_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
        reviewed_manifest_revision=1,
        reviewed_entry=entry,
    )

    assert environment_identities_match(target, target)
    assert not environment_identities_match(
        target, replace(target, runner="developer-laptop")
    )
    assert installation_approval_is_valid(approval, entry)
    assert installation_approval_is_valid(
        approval, replace(entry, verification_recipe="python -VV")
    )
    assert not installation_approval_is_valid(
        approval, replace(entry, install_scope="system-wide")
    )
    assert InstallationApproval.from_dict(approval.to_dict()) == approval


def test_manifest_is_owned_and_committed_by_split_tracking_repository(
    tmp_path: Path, target: EnvironmentIdentity
) -> None:
    target_repo = make_repo(tmp_path / "target")
    tracking_repo = make_repo(tmp_path / "tracking")
    (target_repo / "cascade.toml").write_text(
        f'tracking_repository = "{tracking_repo}"\n', encoding="utf-8"
    )
    for repo in (target_repo, tracking_repo):
        (repo / "README.md").write_text("repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True)
    target_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=target_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prepare_up(target_repo)
    add_doc(
        target_repo,
        id="epic_001",
        title="Tracked",
        tier="epic",
        status="active",
    )

    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, True, ()),
        root=target_repo,
    )

    stored = list(
        (tracking_repo / "docs" / "epics" / "2_active" / "_dependency_manifests").glob(
            "*.json"
        )
    )
    assert [path.name for path in stored] == ["epic_001.json"]
    assert not (
        target_repo / "docs" / "epics" / "2_active" / "_dependency_manifests"
    ).exists()
    current_target_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=target_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert current_target_head == target_head
