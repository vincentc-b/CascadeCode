"""Bounded review-rebase turn preflight (task_035_002_001)."""

import json
import subprocess
from pathlib import Path

from cascade.resolution_actions import admit_resolution_action, normalize_operator_request
from cascade.review_rebase import prepare_review_rebase_turn
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
