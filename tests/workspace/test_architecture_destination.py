"""Architecture destination, path, and durable ownership contracts."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.workspace import (
    ArchitectureArtifactRef,
    ProjectContext,
    WorkspaceError,
    architecture_artifact_link,
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    load_design_ownerships,
    read_architecture_artifact,
    read_project_configuration,
    replay_architecture_artifact,
    resolve_artifact_ref_path,
    resolve_design_ownership,
)


def test_architecture_destination_defaults_to_target(tmp_path: Path) -> None:
    config = tmp_path / "cascade.toml"
    config.write_text("# defaults\n", encoding="utf-8")

    settings = read_project_configuration(config)
    project = ProjectContext.colocated(tmp_path)

    assert settings.architecture_destination == "target"
    assert project.design_path() == tmp_path / "DESIGN.md"
    assert project.design_path("cascade/workspace") == (
        tmp_path / "cascade" / "workspace" / "DESIGN.md"
    )
    assert project.editable_architecture_root == (
        tmp_path / "architecture" / project.target_repository_key
    )


def test_tracking_destination_requires_a_tracking_repository(tmp_path: Path) -> None:
    config = tmp_path / "cascade.toml"
    config.write_text('[architecture]\ndestination = "tracking"\n', encoding="utf-8")

    with pytest.raises(WorkspaceError, match="requires.*tracking_repository"):
        read_project_configuration(config)


@pytest.mark.parametrize(
    "body",
    [
        '[architecture]\ndestination = "elsewhere"\n',
        "[architecture]\ndestination = 3\n",
        'architecture = "tracking"\n',
    ],
)
def test_invalid_architecture_configuration_is_actionable(
    tmp_path: Path, body: str
) -> None:
    config = tmp_path / "cascade.toml"
    config.write_text(body, encoding="utf-8")

    with pytest.raises(WorkspaceError, match="architecture"):
        read_project_configuration(config)


def test_tracking_paths_include_immutable_target_key(tmp_path: Path) -> None:
    target = tmp_path / "product" / "same-name"
    tracking = tmp_path / "planning"
    target.mkdir(parents=True)
    tracking.mkdir()
    project = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )

    assert project.design_path() == (
        tracking / "design" / project.target_repository_key / "DESIGN.md"
    )
    assert project.design_path("cascade/workspace") == (
        tracking
        / "design"
        / project.target_repository_key
        / "cascade"
        / "workspace"
        / "DESIGN.md"
    )
    assert project.editable_architecture_root == (
        tracking / "architecture" / project.target_repository_key
    )
    assert "same-name" not in project.target_repository_key


def test_design_ownership_round_trips_without_basename_inference(
    tmp_path: Path,
) -> None:
    target = tmp_path / "one" / "repository"
    tracking = tmp_path / "tracking"
    target.mkdir(parents=True)
    tracking.mkdir()
    first = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )

    ownership = resolve_design_ownership(first, "cascade/workspace")
    reloaded = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )

    assert reloaded.target_repository_key == first.target_repository_key
    assert load_design_ownerships(reloaded) == (ownership,)
    payload = json.loads(reloaded.design_ownership_path.read_text(encoding="utf-8"))
    assert payload == {
        "version": 1,
        "target_repository_key": first.target_repository_key,
        "designs": {
            "cascade/workspace": {
                "artifact_id": (
                    f"design:{first.target_repository_key}:cascade/workspace"
                ),
                "code_directory": "cascade/workspace",
                "design_owner_directory": "cascade/workspace",
            }
        },
    }
    assert reloaded.design_ownership_path == (
        target / "architecture" / "design-mappings.json"
    )

    other_target = tmp_path / "two" / "repository"
    other_target.mkdir(parents=True)
    assert (
        ProjectContext.split(other_target, tracking).target_repository_key
        != first.target_repository_key
    )


def test_target_key_survives_architecture_destination_change(tmp_path: Path) -> None:
    target = tmp_path / "target"
    tracking = tmp_path / "tracking"
    target.mkdir()
    tracking.mkdir()

    target_mode = ProjectContext.split(target, tracking)
    tracking_mode = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )

    assert target_mode.target_repository_key == tracking_mode.target_repository_key
    assert target_mode.design_path("src") == target / "src" / "DESIGN.md"
    assert tracking_mode.design_path("src") == (
        tracking
        / "design"
        / target_mode.target_repository_key
        / "src"
        / "DESIGN.md"
    )


def test_target_key_survives_checkout_rename_and_root_design_is_untouched(
    tmp_path: Path,
) -> None:
    original = tmp_path / "original"
    original.mkdir()
    root_design = original / "DESIGN.md"
    root_design.write_text("# Existing design\n", encoding="utf-8")
    first = ProjectContext.colocated(original)
    resolve_design_ownership(first, ".")
    key = first.target_repository_key

    renamed = tmp_path / "renamed"
    original.rename(renamed)
    reloaded = ProjectContext.colocated(renamed)

    assert reloaded.target_repository_key == key
    assert root_design.name == "DESIGN.md"
    assert (renamed / "DESIGN.md").read_text(encoding="utf-8") == "# Existing design\n"


def test_persisted_artifact_ref_ignores_later_destination_config(
    tmp_path: Path,
) -> None:
    target = _committed_repo(tmp_path / "target")
    tracking = _committed_repo(tmp_path / "tracking")
    tracking_mode = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )
    resolve_design_ownership(tracking_mode, "cascade/workspace")
    design = tracking_mode.design_path("cascade/workspace")
    design.parent.mkdir(parents=True)
    design.write_text("# Reviewed design\n", encoding="utf-8")
    _git(target=tracking, args=("add", "."))
    _git(target=tracking, args=("commit", "-m", "add reviewed design"))

    created = create_architecture_artifact_ref(
        tracking_mode,
        "cascade/workspace",
        owning_work="feat_034_001",
    )
    persisted = ArchitectureArtifactRef.from_dict(created.to_dict())
    target_mode = ProjectContext.split(target, tracking)

    assert persisted.destination_repository_role == "tracking"
    assert persisted.revision == _git(target=tracking, args=("rev-parse", "HEAD"))
    assert resolve_artifact_ref_path(target_mode, persisted) == (
        tracking
        / "design"
        / target_mode.target_repository_key
        / "cascade"
        / "workspace"
        / "DESIGN.md"
    )
    assert target_mode.design_path("cascade/workspace") == (
        target / "cascade" / "workspace" / "DESIGN.md"
    )


def test_artifact_ref_requires_persisted_owner_and_committed_key_is_immutable(
    tmp_path: Path,
) -> None:
    target = _committed_repo(tmp_path / "target")
    project = ProjectContext.colocated(target)

    with pytest.raises(WorkspaceError, match="no persisted design ownership"):
        create_architecture_artifact_ref(
            project,
            "unmapped",
            owning_work="feat_034_001",
        )

    resolve_design_ownership(project, ".")
    _git(target=target, args=("add", "architecture/design-mappings.json"))
    _git(target=target, args=("commit", "-m", "record architecture identity"))
    payload = json.loads(project.design_ownership_path.read_text(encoding="utf-8"))
    payload["target_repository_key"] = f"target-{'0' * 32}"
    project.design_ownership_path.write_text(
        json.dumps(payload), encoding="utf-8"
    )

    with pytest.raises(WorkspaceError, match="differs from the committed"):
        _ = project.target_repository_key


def test_reads_links_proposals_and_replay_use_the_fixed_reference(
    tmp_path: Path,
) -> None:
    target = _committed_repo(tmp_path / "target")
    tracking = _committed_repo(tmp_path / "tracking")
    config = target / "cascade.toml"
    config.write_text(
        f'tracking_repository = "{tracking}"\n\n'
        '[architecture]\ndestination = "tracking"\n',
        encoding="utf-8",
    )
    settings = read_project_configuration(config)
    tracking_mode = ProjectContext.split(
        target,
        tracking,
        architecture_destination=settings.architecture_destination,
    )
    resolve_design_ownership(tracking_mode, "cascade/workspace")
    _git(target=target, args=("add", "architecture/design-mappings.json"))
    _git(target=target, args=("commit", "-m", "record design mapping"))
    design = tracking_mode.design_path("cascade/workspace")
    design.parent.mkdir(parents=True)
    design.write_text("# Reviewed design\n", encoding="utf-8")
    _git(target=tracking, args=("add", "."))
    _git(target=tracking, args=("commit", "-m", "add reviewed design"))

    reference = create_architecture_artifact_ref(
        tracking_mode, "cascade/workspace", owning_work="feat_034_001"
    )
    expected_link = (
        f"architecture:{reference.destination_repository_key}"
        f"@{reference.revision}:{reference.repository_path.as_posix()}"
    )

    design.write_text("# Later design\n", encoding="utf-8")
    _git(target=tracking, args=("add", "."))
    _git(target=tracking, args=("commit", "-m", "change design"))
    config.write_text(
        f'tracking_repository = "{tracking}"\n\n'
        '[architecture]\ndestination = "target"\n',
        encoding="utf-8",
    )
    reconfigured = read_project_configuration(config)
    target_mode = ProjectContext.split(
        target,
        tracking,
        architecture_destination=reconfigured.architecture_destination,
    )

    assert resolve_artifact_ref_path(target_mode, reference) == design
    assert read_architecture_artifact(target_mode, reference) == "# Reviewed design\n"
    assert replay_architecture_artifact(target_mode, reference) == "# Reviewed design\n"
    assert architecture_artifact_link(reference) == expected_link
    assert target_mode.design_path("cascade/workspace") != design
    assert load_design_ownerships(target_mode)[0].artifact_id == (
        f"design:{reference.target_repository_key}:cascade/workspace"
    )

    mismatched_repository = replace(
        reference, destination_repository_key="repository-mismatch"
    )
    with pytest.raises(WorkspaceError, match="destination repository has changed"):
        read_architecture_artifact(target_mode, mismatched_repository)

    missing_blob = replace(reference, repository_path=Path("missing/DESIGN.md"))
    with pytest.raises(WorkspaceError, match="cannot read pinned architecture artifact"):
        read_architecture_artifact(target_mode, missing_blob)

    replacement_tracking = _committed_repo(tmp_path / "replacement-tracking")
    changed_tracking_repository = ProjectContext.split(
        target, replacement_tracking, architecture_destination="tracking"
    )
    with pytest.raises(WorkspaceError, match="destination repository has changed"):
        read_architecture_artifact(changed_tracking_repository, reference)


def test_artifact_ref_requires_reviewed_bytes_to_be_committed(
    tmp_path: Path,
) -> None:
    target = _committed_repo(tmp_path / "target")
    project = ProjectContext.colocated(target)
    resolve_design_ownership(project, ".")
    design = project.design_path()
    design.write_text("# Uncommitted design\n", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="reviewed bytes are not committed"):
        create_architecture_artifact_ref(
            project, ".", owning_work="feat_034_001"
        )


def test_artifact_ref_rejects_tracked_working_bytes_that_differ_from_head(
    tmp_path: Path,
) -> None:
    target = _committed_repo(tmp_path / "target")
    project = ProjectContext.colocated(target)
    resolve_design_ownership(project, ".")
    design = project.design_path()
    design.write_text("# Committed design\n", encoding="utf-8")
    _git(target=target, args=("add", "."))
    _git(target=target, args=("commit", "-m", "add reviewed design"))
    design.write_text("# Uncommitted replacement\n", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="working bytes differ"):
        create_architecture_artifact_ref(
            project, ".", owning_work="feat_034_001"
        )


def test_model_reference_routes_under_fixed_editable_architecture_root(
    tmp_path: Path,
) -> None:
    target = _committed_repo(tmp_path / "target")
    tracking = _committed_repo(tmp_path / "tracking")
    project = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )
    resolve_design_ownership(project, "cascade/workspace")
    model = project.editable_architecture_root / "workspace.dsl"
    model.parent.mkdir(parents=True)
    model.write_text("workspace model\n", encoding="utf-8")
    _git(target=tracking, args=("add", "."))
    _git(target=tracking, args=("commit", "-m", "add architecture model"))

    reference = create_architecture_model_ref(
        project,
        "cascade/workspace",
        "workspace.dsl",
        owning_work="feat_034_001",
    )
    pinned_revision = _git(target=tracking, args=("rev-parse", "HEAD"))
    model.write_text("later workspace model\n", encoding="utf-8")
    _git(target=tracking, args=("add", "."))
    _git(target=tracking, args=("commit", "-m", "change architecture model"))
    reconfigured = ProjectContext.split(target, tracking)

    assert reference.revision == pinned_revision
    assert resolve_artifact_ref_path(reconfigured, reference) == model
    assert read_architecture_artifact(reconfigured, reference) == "workspace model\n"
    assert replay_architecture_artifact(reconfigured, reference) == "workspace model\n"


def test_artifact_reference_rejects_untrusted_revision() -> None:
    with pytest.raises(WorkspaceError, match="revision"):
        ArchitectureArtifactRef(
            target_repository_key=f"target-{'0' * 32}",
            code_directory=Path("."),
            design_owner_directory=Path("."),
            owning_work="feat_034_001",
            destination_repository_key="repository-key",
            destination_repository_role="target",
            repository_path=Path("DESIGN.md"),
            revision="--help",
        )


def _committed_repo(parent: Path) -> Path:
    root = parent / "repo"
    root.mkdir(parents=True)
    _git(target=root, args=("init", "-b", "main"))
    _git(target=root, args=("config", "user.email", "test@example.com"))
    _git(target=root, args=("config", "user.name", "Test User"))
    (root / "README.md").write_text("repository\n", encoding="utf-8")
    _git(target=root, args=("add", "README.md"))
    _git(target=root, args=("commit", "-m", "initial"))
    return root


def _git(*, target: Path, args: tuple[str, ...]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=target,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
