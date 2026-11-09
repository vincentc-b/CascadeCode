"""Project-startup coverage for explicit target and tracking repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.workspace import WorkspaceError, init_workspace, prepare_up
from tests.support import make_git_repo


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )


def _startable_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = make_git_repo(tmp_path)
    init_workspace(root)
    (root / "README.md").write_text("workspace\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initialize workspace")
    return root


def test_startup_without_tracking_configuration_preserves_colocated_behavior(
    tmp_path: Path,
) -> None:
    root = _startable_repo(tmp_path)

    workspace = prepare_up(root)

    assert workspace.config == root / "cascade.toml"
    assert workspace.target_repository is workspace.tracking_repository
    assert workspace.target_repository.root == root
    assert workspace.path == workspace.target_repository.root
    assert workspace.board == workspace.target_repository.root / "docs"
    assert workspace.runtime == workspace.target_repository.root / ".cascade"


@pytest.mark.parametrize("config_name", ["cascade.toml", "cascade.yaml"])
def test_startup_resolves_split_repository_roles_from_toml_and_yaml(
    tmp_path: Path, config_name: str
) -> None:
    root = _startable_repo(tmp_path / "target")
    tracking_parent = tmp_path / "tracking"
    tracking_parent.mkdir()
    tracking = make_git_repo(tracking_parent)
    config = root / config_name
    if config_name.endswith(".toml"):
        config.write_text(
            'tracking_repository = "../../tracking/repo"\n', encoding="utf-8"
        )
    else:
        (root / "cascade.toml").unlink()
        config.write_text(
            'tracking_repository: "../../tracking/repo"\n', encoding="utf-8"
        )

    workspace = prepare_up(root)

    assert workspace.config == config
    assert workspace.target_repository is not workspace.tracking_repository
    assert workspace.target_repository.root == root
    assert workspace.tracking_repository.root == tracking
    assert workspace.path == workspace.target_repository.root


def test_startup_resolves_tracking_architecture_destination(tmp_path: Path) -> None:
    root = _startable_repo(tmp_path / "target")
    tracking_parent = tmp_path / "tracking"
    tracking_parent.mkdir()
    tracking = make_git_repo(tracking_parent)
    (root / "cascade.toml").write_text(
        f'tracking_repository = "{tracking}"\n\n'
        '[architecture]\ndestination = "tracking"\n',
        encoding="utf-8",
    )

    workspace = prepare_up(root)

    assert workspace.project is not None
    assert workspace.project.architecture_destination == "tracking"
    assert workspace.project.architecture_repository.root == tracking
    assert workspace.project.design_path("cascade") == (
        tracking
        / "design"
        / workspace.project.target_repository_key
        / "cascade"
        / "DESIGN.md"
    )


@pytest.mark.parametrize("unavailable", ["missing", "not-a-checkout"])
def test_unavailable_tracking_repository_stops_startup(
    tmp_path: Path, unavailable: str
) -> None:
    root = _startable_repo(tmp_path / "target")
    tracking = tmp_path / unavailable
    if unavailable == "not-a-checkout":
        tracking.mkdir()
    (root / "cascade.toml").write_text(
        f'tracking_repository = "{tracking}"\n', encoding="utf-8"
    )

    with pytest.raises(WorkspaceError) as raised:
        prepare_up(root)

    message = str(raised.value)
    assert "tracking repository" in message
    assert "does not exist" in message or "not a usable Git checkout" in message


def test_tracking_clone_failure_stops_startup_with_redacted_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _startable_repo(tmp_path)
    (root / "cascade.toml").write_text(
        'tracking_repository = "https://user:token@example.test/planning.git"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cascade.workspace.repository_resolver._git_clone",
        lambda _remote, _checkout: subprocess.CompletedProcess(
            args=["git", "clone"],
            returncode=1,
            stdout="",
            stderr="fatal: authentication failed for helper-secret",
        ),
    )

    with pytest.raises(WorkspaceError) as raised:
        prepare_up(root)

    message = str(raised.value)
    assert "authentication failed" in message
    assert "verify the configured Git credentials or SSH access" in message
    assert "https://example.test/planning.git" in message
    assert "user" not in message
    assert "token" not in message
    assert "helper-secret" not in message
