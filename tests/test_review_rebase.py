"""Bounded review-rebase turn preflight (task_035_002_001)."""

import json
import subprocess
from pathlib import Path

from cascade.resolution_actions import admit_resolution_action, normalize_operator_request
from cascade.review_rebase import execute_review_rebase, prepare_review_rebase_turn
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
