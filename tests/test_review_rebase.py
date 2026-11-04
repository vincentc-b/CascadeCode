"""Bounded review-rebase turn preflight (task_035_002_001)."""

import json
import subprocess
from pathlib import Path

from cascade.resolution_actions import admit_resolution_action, normalize_operator_request
import sys

import cascade.review_rebase as review_rebase
from cascade.review_rebase import (
    check_and_publish_review_rebase,
    execute_review_rebase,
    prepare_review_rebase_turn,
)
from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
from tests.test_resolution_actions import _admission_ready_root


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _ready_action(tmp_path: Path) -> tuple[Path, str]:
    root, payload = _admission_ready_root(tmp_path)
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "origin", "feat/feat_035_001", "epic/epic_035")
    admitted = admit_resolution_action(normalize_operator_request(payload), root=root)
    assert admitted.action["status"] == "mutation_ready"
    return root, admitted.action_id


def test_preflight_returns_only_bounded_capabilities_after_fetch(tmp_path: Path) -> None:
    root, action_id = _ready_action(tmp_path)

    result = prepare_review_rebase_turn(action_id, root=root)

    assert result.blocker is None
    assert result.turn is not None
    assert result.turn.worktree == root
    assert result.turn.allowed_operations == (
        "rebase_owned_source",
        "edit_conflicted_owned_paths",
        "run_repository_checks",
        "push_source_with_force_with_lease",
    )
    assert result.turn.initial_state.dirty_paths == ()
    assert result.turn.fetched_remote_shas == (
        result.turn.observed_source_sha,
        result.turn.observed_target_sha,
    )


def test_preflight_preserves_dirty_user_work_and_does_not_fetch(tmp_path: Path) -> None:
    root, action_id = _ready_action(tmp_path)
    (root / "operator-notes.txt").write_text("do not discard\n", encoding="utf-8")

    result = prepare_review_rebase_turn(action_id, root=root)

    assert result.turn is None
    assert result.blocker is not None
    assert result.blocker.code == "dirty_unrelated_paths"
    assert (root / "operator-notes.txt").read_text(encoding="utf-8") == "do not discard\n"


def test_preflight_stops_when_durable_review_authorization_changes(tmp_path: Path) -> None:
    root, action_id = _ready_action(tmp_path)
    path = root / ".cascade" / "reviews.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    records["feat_035_001"]["target_branch"] = "epic/other"
    path.write_text(json.dumps(records), encoding="utf-8")

    result = prepare_review_rebase_turn(action_id, root=root)

    assert result.turn is None
    assert result.blocker is not None
    assert result.blocker.code == "authorization_changed"


def test_preflight_stops_when_fetched_remote_head_changes(tmp_path: Path) -> None:
    root, action_id = _ready_action(tmp_path)
    remote = _git(root, "remote", "get-url", "origin")
    updater = tmp_path / "updater"
    _git(tmp_path, "clone", remote, str(updater))
    _git(updater, "config", "user.email", "test@example.com")
    _git(updater, "config", "user.name", "Test User")
    _git(updater, "checkout", "feat/feat_035_001")
    (updater / "remote-change.txt").write_text("advance\n", encoding="utf-8")
    _git(updater, "add", "remote-change.txt")
    _git(updater, "commit", "-m", "advance remote source")
    _git(updater, "push", "origin", "HEAD:feat/feat_035_001")

    result = prepare_review_rebase_turn(action_id, root=root)

    assert result.turn is None
    assert result.blocker is not None
    assert result.blocker.code == "remote_heads_changed"


def _execution_ready_turn(tmp_path: Path, *, conflict: bool = False):
    root, payload = _admission_ready_root(tmp_path)
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    _git(root, "remote", "add", "origin", str(remote))

    if conflict:
        (root / "unrelated-user-work.txt").write_text("keep this work\n", encoding="utf-8")
        _git(root, "add", "unrelated-user-work.txt")
        _git(root, "commit", "-m", "preserve unrelated user work")
        _git(root, "branch", "-f", "feat/feat_035_001", "HEAD")
        _git(root, "branch", "-f", "epic/epic_035", "HEAD")

    _git(root, "checkout", "epic/epic_035")
    changed_path = "shared.txt" if conflict else "target.txt"
    (root / changed_path).write_text("target\n", encoding="utf-8")
    _git(root, "add", changed_path)
    _git(root, "commit", "-m", "target change")
    target_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "feat/feat_035_001")
    changed_path = "shared.txt" if conflict else "source.txt"
    (root / changed_path).write_text("source\n", encoding="utf-8")
    _git(root, "add", changed_path)
    _git(root, "commit", "-m", "source change")
    source_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "feat/feat_035_001", "epic/epic_035")

    records_path = root / ".cascade" / "reviews.json"
    records_path.parent.mkdir(exist_ok=True)
    records = {
        "feat_035_001": {
            "url": "https://forge.example/repo/pull/147",
            "number": "147",
            "source_branch": "feat/feat_035_001",
            "target_branch": "epic/epic_035",
            "source_head": source_sha,
            "target_head": target_sha,
            "credentials_available": True,
            "resolution_permitted": True,
        }
    }
    records_path.write_text(json.dumps(records), encoding="utf-8")
    save_registry(
        root,
        [IntegrationWorktree("feature", "feat_035_001", "feat/feat_035_001", root, source_sha)],
    )
    payload.update(observed_source_head=source_sha, observed_target_head=target_sha)
    admitted = admit_resolution_action(normalize_operator_request(payload), root=root)
    preflight = prepare_review_rebase_turn(admitted.action_id, root=root)
    assert preflight.turn is not None
    return root, preflight.turn


def test_execution_rebases_only_owned_changed_paths(tmp_path: Path) -> None:
    root, turn = _execution_ready_turn(tmp_path)

    result = execute_review_rebase(turn, authorized_paths=("source.txt",))

    assert result.rebased is True
    assert result.blocker is None
    assert result.modified_paths == ("source.txt",)
    assert _git(root, "merge-base", "--is-ancestor", turn.observed_target_sha, "HEAD") == ""


def test_execution_preserves_unauthorized_conflict_without_a_resolution(tmp_path: Path) -> None:
    root, turn = _execution_ready_turn(tmp_path, conflict=True)

    result = execute_review_rebase(turn, authorized_paths=("other.txt",))

    assert result.rebased is False
    assert result.blocker is not None
    assert result.blocker.code == "conflict_path_not_authorized"
    assert result.conflicted_paths == ("shared.txt",)
    assert (root / ".git" / "rebase-merge").is_dir() or (root / ".git" / "rebase-apply").is_dir()


def test_execution_stops_authorized_semantic_conflict_for_human_decision(tmp_path: Path) -> None:
    root, turn = _execution_ready_turn(tmp_path, conflict=True)

    result = execute_review_rebase(turn, authorized_paths=("shared.txt",))

    assert result.rebased is False
    assert result.blocker is not None
    assert result.blocker.code == "semantic_conflict_requires_decision"
    assert result.conflicted_paths == ("shared.txt",)
    assert "<<<<<<<" in (root / "shared.txt").read_text(encoding="utf-8")


def test_checks_then_publishes_same_source_with_explicit_lease(tmp_path: Path, monkeypatch) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    rebased = execute_review_rebase(turn, authorized_paths=("source.txt",))
    monkeypatch.setattr(review_rebase, "_REPOSITORY_CHECK_COMMAND", (sys.executable, "-c", ""))

    publication = check_and_publish_review_rebase(turn, rebased)

    assert publication.published is True
    assert publication.blocker is None
    assert publication.observed_remote_source_sha == turn.observed_source_sha
    assert publication.checks[0].returncode == 0
    assert _git(root, "rev-parse", "origin/feat/feat_035_001") == rebased.source_head
    assert _git(root, "rev-parse", "origin/epic/epic_035") == turn.observed_target_sha


def test_failed_checks_preserve_rebased_work_and_skip_publication(tmp_path: Path, monkeypatch) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    rebased = execute_review_rebase(turn, authorized_paths=("source.txt",))
    monkeypatch.setattr(review_rebase, "_REPOSITORY_CHECK_COMMAND", (sys.executable, "-c", "raise SystemExit(1)"))

    publication = check_and_publish_review_rebase(turn, rebased)

    assert publication.published is False
    assert publication.blocker is not None
    assert publication.blocker.code == "repository_checks_failed"
    assert publication.checks[0].returncode == 1
    assert _git(root, "rev-parse", "origin/feat/feat_035_001") == turn.observed_source_sha
    assert _git(root, "rev-parse", "HEAD") == rebased.source_head


def test_changed_remote_source_after_checks_stops_before_lease_push(tmp_path: Path, monkeypatch) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    rebased = execute_review_rebase(turn, authorized_paths=("source.txt",))
    monkeypatch.setattr(review_rebase, "_REPOSITORY_CHECK_COMMAND", (sys.executable, "-c", ""))
    remote = _git(root, "remote", "get-url", "origin")
    updater = tmp_path / "updater-after-rebase"
    _git(tmp_path, "clone", remote, str(updater))
    _git(updater, "config", "user.email", "test@example.com")
    _git(updater, "config", "user.name", "Test User")
    _git(updater, "checkout", turn.source_ref)
    (updater / "concurrent.txt").write_text("advance\n", encoding="utf-8")
    _git(updater, "add", "concurrent.txt")
    _git(updater, "commit", "-m", "concurrent source advance")
    advanced = _git(updater, "rev-parse", "HEAD")
    _git(updater, "push", "origin", f"HEAD:{turn.source_ref}")

    publication = check_and_publish_review_rebase(turn, rebased)

    assert publication.published is False
    assert publication.blocker is not None
    assert publication.blocker.code == "source_remote_changed"
    assert publication.observed_remote_source_sha == advanced
    assert _git(root, "rev-parse", "HEAD") == rebased.source_head


def test_end_to_end_clean_owned_rebase_records_evidence_and_updates_only_review_source(
    tmp_path: Path, monkeypatch
) -> None:
    """Exercise admission through publication against a disposable bare remote."""

    root, turn = _execution_ready_turn(tmp_path)
    commands: list[tuple[str, ...]] = []
    authorization_calls = 0
    run = subprocess.run
    authorized_action = review_rebase._authorized_action

    def record_command(command, *args, **kwargs):
        if isinstance(command, list):
            commands.append(tuple(command))
        return run(command, *args, **kwargs)

    def record_authorization(*args, **kwargs):
        nonlocal authorization_calls
        authorization_calls += 1
        return authorized_action(*args, **kwargs)

    monkeypatch.setattr(review_rebase, "_REPOSITORY_CHECK_COMMAND", (sys.executable, "-c", ""))
    monkeypatch.setattr(review_rebase.subprocess, "run", record_command)
    monkeypatch.setattr(review_rebase, "_authorized_action", record_authorization)

    execution = execute_review_rebase(turn, authorized_paths=("source.txt",))
    publication = check_and_publish_review_rebase(turn, execution)

    assert execution.rebased is True
    assert publication.published is True
    assert turn.initial_state.remote_shas == (turn.observed_source_sha, turn.observed_target_sha)
    assert turn.fetched_remote_shas == (turn.observed_source_sha, turn.observed_target_sha)
    assert authorization_calls == 1  # publication revalidates the admitted authorization
    assert publication.checks and publication.checks[0].returncode == 0
    assert publication.observed_remote_source_sha == turn.observed_source_sha
    assert _git(root, "ls-remote", "origin", f"refs/heads/{turn.source_ref}").split()[0] == execution.source_head
    assert _git(root, "ls-remote", "origin", f"refs/heads/{turn.target_ref}").split()[0] == turn.observed_target_sha
    assert (
        "git",
        "push",
        "origin",
        f"--force-with-lease=refs/heads/{turn.source_ref}:{turn.observed_source_sha}",
        f"HEAD:refs/heads/{turn.source_ref}",
    ) in commands


def test_end_to_end_semantic_conflict_stops_with_recoverable_owned_work(tmp_path: Path) -> None:
    """An owned conflict is not guessed at and neither remote review ref moves."""

    root, turn = _execution_ready_turn(tmp_path, conflict=True)

    execution = execute_review_rebase(turn, authorized_paths=("shared.txt",))

    assert execution.rebased is False
    assert execution.blocker is not None
    assert execution.blocker.code == "semantic_conflict_requires_decision"
    assert execution.conflicted_paths == ("shared.txt",)
    assert (root / "shared.txt").read_text(encoding="utf-8").startswith("<<<<<<<")
    assert (root / "unrelated-user-work.txt").read_text(encoding="utf-8") == "keep this work\n"
    assert _git(root, "rev-parse", f"refs/heads/{turn.source_ref}") == turn.observed_source_sha
    assert _git(root, "ls-remote", "origin", f"refs/heads/{turn.source_ref}").split()[0] == turn.observed_source_sha
    assert _git(root, "ls-remote", "origin", f"refs/heads/{turn.target_ref}").split()[0] == turn.observed_target_sha
    assert (root / ".git" / "rebase-merge").is_dir() or (root / ".git" / "rebase-apply").is_dir()
