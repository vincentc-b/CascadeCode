"""Tracking-repository project configuration and repository-role contexts."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.workspace import (
    ProjectContext,
    WorkspaceError,
    find_project_config,
    init_workspace,
    read_tracking_repository,
)
from tests.support import make_git_repo


@pytest.mark.parametrize("name", ["cascade.toml", "cascade.yaml", "cascade.yml"])
def test_tracking_repository_local_reference_is_equivalent_across_formats(
    tmp_path: Path, name: str
) -> None:
    config_dir = tmp_path / "project" / "config"
    config_dir.mkdir(parents=True)
    config = config_dir / name
    if name.endswith(".toml"):
        config.write_text('tracking_repository = "../planning"\n', encoding="utf-8")
    else:
        config.write_text('tracking_repository: "../planning"\n', encoding="utf-8")

    reference = read_tracking_repository(config)

    assert reference is not None
    assert reference.kind == "local"
    assert reference.local_path == (config_dir.parent / "planning").resolve()
    assert reference.remote_url is None


@pytest.mark.parametrize("name", ["cascade.toml", "cascade.yaml"])
def test_tracking_repository_remote_reference_is_equivalent_across_formats(
    tmp_path: Path, name: str
) -> None:
    config = tmp_path / name
    if name.endswith(".toml"):
        config.write_text(
            'tracking_repository = "git@github.com:example/planning.git"\n',
            encoding="utf-8",
        )
    else:
        config.write_text(
            'tracking_repository: "git@github.com:example/planning.git"\n',
            encoding="utf-8",
        )

    reference = read_tracking_repository(config)

    assert reference is not None
    assert reference.kind == "remote"
    assert reference.remote_url == "git@github.com:example/planning.git"
    assert reference.local_path is None


def test_scp_remote_without_owner_path_is_supported(tmp_path: Path) -> None:
    config = tmp_path / "cascade.toml"
    config.write_text(
        'tracking_repository = "git@example.com:planning.git"\n', encoding="utf-8"
    )

    reference = read_tracking_repository(config)

    assert reference is not None
    assert reference.kind == "remote"


def test_relative_reference_is_anchored_to_config_not_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "nested" / "settings"
    config_dir.mkdir(parents=True)
    config = config_dir / "cascade.toml"
    config.write_text('tracking_repository = "../../tracking"\n', encoding="utf-8")
    unrelated = tmp_path / "elsewhere"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    reference = read_tracking_repository(config)

    assert reference is not None
    assert reference.local_path == (tmp_path / "tracking").resolve()


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("cascade.toml", "tracking_repository = 42\n"),
        ("cascade.yaml", "tracking_repository: []\n"),
        ("cascade.toml", 'tracking_repository = "ftp://secret@example.com/repo.git"\n'),
        ("cascade.yaml", 'tracking_repository: "https://secret@example.com"\n'),
        ("cascade.toml", 'tracking_repository = "https://[secret/repo"\n'),
    ],
)
def test_unsupported_tracking_values_have_actionable_redacted_errors(
    tmp_path: Path, name: str, body: str
) -> None:
    config = tmp_path / name
    config.write_text(body, encoding="utf-8")

    with pytest.raises(WorkspaceError) as raised:
        read_tracking_repository(config)

    message = str(raised.value)
    assert "tracking_repository" in message
    assert "secret" not in message


def test_omission_preserves_colocated_workspace_context(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)

    workspace = init_workspace(root)

    assert workspace.target_repository is workspace.tracking_repository
    assert workspace.target_repository.root == root.resolve()
    assert workspace.project == ProjectContext.colocated(root)
    assert read_tracking_repository(workspace.config) is None


def test_project_context_names_distinct_split_repository_roles(tmp_path: Path) -> None:
    context = ProjectContext.split(tmp_path / "target", tmp_path / "tracking")

    assert context.target is not context.tracking
    assert context.target.root == (tmp_path / "target").resolve()
    assert context.tracking.root == (tmp_path / "tracking").resolve()


def test_config_discovery_supports_yaml_and_rejects_ambiguous_files(tmp_path: Path) -> None:
    yaml_config = tmp_path / "cascade.yaml"
    yaml_config.write_text("tracking_repository: ../tracking\n", encoding="utf-8")
    assert find_project_config(tmp_path) == yaml_config

    (tmp_path / "cascade.toml").write_text("# duplicate\n", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="multiple Cascade"):
        find_project_config(tmp_path)
