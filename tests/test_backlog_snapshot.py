from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.automation import reset_automation_memory, sync_briefs
from cascade.board.errors import GitError
from cascade.board.store import read_doc
from cascade.watchdog.dispatch import activate_epic
from cascade.workspace.doc_root import read_doc_resolved
from cascade.workspace.backlog_snapshot import (
    read_provenance,
    refresh_remote_backlog_snapshot,
    resolve_epic_brief_base_sha,
    resolve_validated_epic_activation_sha,
    snapshot_root,
)
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_branch,
    merged_board,
)
from tests.support import add_doc, commit_board, make_repo


def _init_bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    return remote


def _connect_and_push(root: Path, remote: Path, *, branch: str = "main") -> None:
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "README.md").write_text("trunk\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=root, check=True, capture_output=True)


def _seed_remote(tmp_path: Path) -> tuple[Path, Path]:
    remote = _init_bare_remote(tmp_path)
    upstream = make_repo(tmp_path / "upstream")
    _connect_and_push(upstream, remote)
    return upstream, remote


def _push_remote_brief(upstream: Path, epic_id: str, title: str) -> None:
    add_doc(upstream, id=epic_id, title=title, tier="epic", status="backlog")
    commit_board(upstream, f"brief {epic_id}")
    subprocess.run(["git", "push", "origin", "main"], cwd=upstream, check=True, capture_output=True)


def _enable_automation(root: Path, remote: str = "origin") -> None:
    (root / "cascade.toml").write_text(
        f'[automation]\nenabled = true\npoll_seconds = 1\nremote = "{remote}"\n',
        encoding="utf-8",
    )


def test_refresh_publishes_snapshot_and_merged_board(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_010", "Remote epic")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "local.txt").write_text("cascade-only\n", encoding="utf-8")
    subprocess.run(["git", "add", "local.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local"], cwd=root, check=True, capture_output=True)

    result = refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    assert result.unchanged is False
    provenance = read_provenance(root)
    assert provenance is not None
    assert len(provenance.sha) == 40
    assert (snapshot_root(root) / "docs/epics/1_backlog").is_dir()
    board = merged_board(root)
    assert "epic_010" in board.by_id
    assert resolve_epic_brief_base_sha("epic_010", trunk=root) == provenance.sha


def test_provenance_survives_restart(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_011", "Persist me")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    first = read_provenance(root)
    assert first is not None
    second = read_provenance(root)
    assert second == first


def test_missing_remote_ref_preserves_last_snapshot(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_012", "Keep me")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    good = read_provenance(root)
    with pytest.raises(GitError, match="has no branch 'missing'"):
        refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="missing")
    assert read_provenance(root) == good
    assert "epic_012" in merged_board(root).by_id


def test_fetch_failure_retains_snapshot(tmp_path: Path, monkeypatch) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_013", "Stable")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    before = read_provenance(root)

    def boom(args, root_path, check=True):
        if args[:2] == ["fetch", "origin"]:
            return subprocess.CompletedProcess(args, 1, "", "network down")
        raise AssertionError(args)

    monkeypatch.setattr("cascade.workspace.backlog_snapshot.git_run", boom)
    with pytest.raises(GitError, match="network down"):
        refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    assert read_provenance(root) == before


def test_malformed_remote_brief_keeps_prior_snapshot(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_014", "Valid")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    good = read_provenance(root)

    bad_path = upstream / "docs/epics/1_backlog/epic_015_bad.md"
    bad_path.write_text("not valid frontmatter\n", encoding="utf-8")
    subprocess.run(["git", "add", str(bad_path.relative_to(upstream))], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-m", "bad"], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=upstream, check=True, capture_output=True)

    with pytest.raises(GitError, match="malformed remote brief"):
        refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    assert read_provenance(root) == good


def test_duplicate_remote_ids_fail_closed(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    first = add_doc(upstream, id="epic_020", title="One", tier="epic", status="backlog")
    second_path = upstream / "docs/epics/1_backlog/epic_020_two.md"
    second_path.write_text(first.meta.path.read_text(encoding="utf-8"), encoding="utf-8")
    commit_board(upstream, "dup")
    subprocess.run(["git", "push", "origin", "main"], cwd=upstream, check=True, capture_output=True)

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    with pytest.raises(GitError, match="duplicate epic id epic_020"):
        refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    assert read_provenance(root) is None


def test_atomic_replace_swaps_snapshot_contents(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_021", "First")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    first_sha = read_provenance(root).sha  # type: ignore[union-attr]
    first_files = list((snapshot_root(root) / "docs/epics/1_backlog").glob("*.md"))

    _push_remote_brief(upstream, "epic_022", "Second")
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    second_sha = read_provenance(root).sha  # type: ignore[union-attr]
    second_files = list((snapshot_root(root) / "docs/epics/1_backlog").glob("*.md"))

    assert first_sha != second_sha
    assert {path.name for path in first_files} == {"epic_021_first.md"}
    assert {path.name for path in second_files} == {
        "epic_021_first.md",
        "epic_022_second.md",
    }


def test_local_epic_omits_conflicting_remote_brief(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_030", "Remote")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    add_doc(root, id="epic_030", title="Local active", tier="epic", status="active")
    result = refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    assert "epic_030" in result.omitted_ids
    assert "epic_030" in merged_board(root).by_id
    assert not list((snapshot_root(root) / "docs/epics/1_backlog").glob("epic_030*.md"))


def test_sync_briefs_reports_new_remote_epic_without_ff(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_040", "Imported")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "README.md").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local"], cwd=root, check=True, capture_output=True)
    _enable_automation(root)
    reset_automation_memory()
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    payload = sync_briefs(root, force=True)

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert head_before == head_after
    assert payload["new_briefs"] == ["epic_040"]
    repeat = sync_briefs(root, force=True)
    assert repeat["new_briefs"] == []


def test_activate_snapshot_only_epic_without_trunk_ff(tmp_path: Path, monkeypatch) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_050", "Activate me")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "README.md").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local"], cwd=root, check=True, capture_output=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    provenance = read_provenance(root)
    assert provenance is not None

    monkeypatch.setattr("cascade.watchdog.hooks.invoke_boot", lambda *args, **kwargs: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args, **_kwargs: None)

    branch_before = subprocess.run(
        ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    remote_main = subprocess.run(
        ["git", "rev-parse", "origin/main"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    result = activate_epic("epic_050", "human", root=root)
    branch_after = subprocess.run(
        ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    assert result.ok
    assert branch_before == branch_after == "main"
    assert head_after != remote_main
    from cascade.workspace.integration_worktree import get_integration_worktree

    epic_wt = get_integration_worktree(root, "epic", "epic_050")
    assert epic_wt is not None
    assert epic_wt.base_sha == provenance.sha


def test_snapshot_only_epic_is_readable_from_trunk(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_060", "Readable")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")

    doc = read_doc("epic_060", root=root)
    assert doc.meta.title == "Readable"
    assert read_doc_resolved("epic_060", root=root).meta.id == "epic_060"


def test_merged_board_cache_observes_published_snapshot(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    warm = merged_board(root)
    assert "epic_070" not in warm.by_id

    _push_remote_brief(upstream, "epic_070", "Cached")
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    fresh = merged_board(root)
    assert fresh is not warm
    assert "epic_070" in fresh.by_id


def test_activate_snapshot_epic_after_restart_without_refresh(tmp_path: Path, monkeypatch) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_051", "Restart me")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "README.md").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init local"], cwd=root, check=True, capture_output=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    provenance = read_provenance(root)
    assert provenance is not None

    monkeypatch.setattr("cascade.watchdog.hooks.invoke_boot", lambda *args, **kwargs: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args, **_kwargs: None)

    result = activate_epic("epic_051", "human", root=root)
    assert result.ok
    epic_wt = get_integration_worktree(root, "epic", "epic_051")
    assert epic_wt is not None
    assert epic_wt.base_sha == provenance.sha


def test_activate_snapshot_epic_uses_provenance_not_local_head(tmp_path: Path, monkeypatch) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_052", "Provenance wins")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "README.md").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local"], cwd=root, check=True, capture_output=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    provenance = read_provenance(root)
    assert provenance is not None
    local_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert local_head != provenance.sha
    assert resolve_validated_epic_activation_sha("epic_052", trunk=root) == provenance.sha

    monkeypatch.setattr("cascade.watchdog.hooks.invoke_boot", lambda *args, **kwargs: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args, **_kwargs: None)

    result = activate_epic("epic_052", "human", root=root)
    assert result.ok
    epic_wt = get_integration_worktree(root, "epic", "epic_052")
    assert epic_wt is not None
    assert epic_wt.base_sha == provenance.sha


def test_activate_refuses_stale_snapshot_provenance(tmp_path: Path, monkeypatch) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_053", "Stale")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "README.md").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init local"], cwd=root, check=True, capture_output=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")

    good_sha = read_provenance(root).sha  # type: ignore[union-attr]
    provenance_path = snapshot_root(root) / "provenance.json"
    raw = provenance_path.read_text(encoding="utf-8")
    provenance_path.write_text(raw.replace(good_sha, "0" * 40), encoding="utf-8")

    monkeypatch.setattr("cascade.watchdog.hooks.invoke_boot", lambda *args, **kwargs: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args, **_kwargs: None)

    refused = activate_epic("epic_053", "human", root=root)
    assert refused.ok is False
    assert refused.reason == "brief_not_on_trunk"
    assert get_integration_worktree(root, "epic", "epic_053") is None


def test_activate_failure_leaves_existing_epic_worktree(tmp_path: Path, monkeypatch) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_054", "Will fail")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    add_doc(root, id="epic_001", title="Local epic", tier="epic", status="ready_to_plan")
    commit_board(root, "local epic")
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")

    monkeypatch.setattr("cascade.watchdog.hooks.invoke_boot", lambda *args, **kwargs: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args, **_kwargs: None)

    assert activate_epic("epic_001", "human", root=root).ok
    existing = get_integration_worktree(root, "epic", "epic_001")
    assert existing is not None

    good_sha = read_provenance(root).sha  # type: ignore[union-attr]
    provenance_path = snapshot_root(root) / "provenance.json"
    raw = provenance_path.read_text(encoding="utf-8")
    provenance_path.write_text(raw.replace(good_sha, "0" * 40), encoding="utf-8")

    refused = activate_epic("epic_054", "human", root=root)
    assert refused.ok is False
    assert get_integration_worktree(root, "epic", "epic_001") == existing
    assert _branch_exists(root, integration_branch("epic", "epic_001"))


def _branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def test_sync_briefs_reports_omitted_conflicts(tmp_path: Path) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_080", "Remote")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    add_doc(root, id="epic_080", title="Local wins", tier="epic", status="active")
    _enable_automation(root)
    reset_automation_memory()

    payload = sync_briefs(root, force=True)

    assert payload["new_briefs"] == []
    assert payload["omitted_ids"] == ["epic_080"]
    assert any("epic_080" in item for item in payload["diagnostics"])
    assert merged_board(root).by_id["epic_080"].title == "Local wins"
