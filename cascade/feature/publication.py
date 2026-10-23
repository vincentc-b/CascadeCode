"""Prepare and validate the task-shaped history published for a Feature review."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cascade.board.errors import GitError, NotFound
from cascade.board.store import list_board, read_doc
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_branch,
    locate_trunk,
)

_TRAILER = "Cascade-Task:"
_LIFECYCLE_PREFIXES = (
    "docs/epics/",
    "docs/features/",
    "docs/tasks/",
    "docs/_queue/",
    "docs/_war_room/",
)


@dataclass(frozen=True)
class PublicationHistory:
    base_sha: str
    tip_sha: str
    task_ids: tuple[str, ...]
    commits: tuple[str, ...]
    remote_lease_sha: str | None = None


def prepare_feature_publication(feature_id: str, *, root: Path) -> PublicationHistory:
    """Fold unpublished lifecycle commits into one linear commit per completed Task."""

    trunk = locate_trunk(root)
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"feature worktree missing: {feature_id}")
    source = integration_branch("feature", feature_id)
    target_doc = read_doc(feature_id, root=entry.path)
    publication_ready = (
        target_doc.meta.status == "completed"
        and target_doc.meta.path.parent.name == "3_completed"
    ) or (
        target_doc.meta.status == "active"
        and target_doc.meta.path.parent.name == "2_active"
    )
    if not publication_ready:
        raise GitError(f"{feature_id} must be ready for review publication")

    task_ids = _completed_task_ids(feature_id, entry.path)
    if not task_ids:
        raise GitError(f"{feature_id} has no completed task commits to publish")
    _require_clean(entry.path)

    old_tip = _git(entry.path, "rev-parse", source).stdout.strip()
    remote_ref = f"refs/remotes/origin/{source}"
    remote_tip = _optional_ref(entry.path, remote_ref)
    remote_lease_sha: str | None = None
    if remote_tip is not None:
        if not _is_ancestor(entry.path, entry.base_sha, remote_tip):
            raise GitError(f"{remote_ref} does not descend from the feature publication base")
        try:
            published = validate_feature_publication(
                feature_id,
                source_root=entry.path,
                source_ref=remote_tip,
                base_ref=entry.base_sha,
                expected_task_ids=None,
            )
        except GitError:
            # A feature branch can be pushed before review publication.  Such a
            # branch contains the ordinary lifecycle/checkpoint history and is
            # safe to replace only while it is an ancestor of the local source.
            # Once any publication trailer appears, treat invalid history as a
            # partial publication and fail closed rather than guessing.
            if _range_task_trailers(entry.path, entry.base_sha, remote_tip):
                raise
            recovery_ref = _recovery_ref(feature_id)
            recorded_tip = _optional_ref(entry.path, recovery_ref)
            if _is_ancestor(entry.path, remote_tip, old_tip):
                _git(entry.path, "update-ref", recovery_ref, remote_tip)
                base_sha = entry.base_sha
                new_task_ids = list(task_ids)
                remote_lease_sha = remote_tip
            elif recorded_tip == remote_tip:
                # A previous attempt normalized locally but failed before its
                # leased push.  Reuse only the exact recorded remote tip.
                history = validate_feature_publication(
                    feature_id,
                    source_root=entry.path,
                    source_ref=source,
                    base_ref=entry.base_sha,
                    expected_task_ids=task_ids,
                )
                return PublicationHistory(
                    base_sha=history.base_sha,
                    tip_sha=history.tip_sha,
                    task_ids=history.task_ids,
                    commits=history.commits,
                    remote_lease_sha=remote_tip,
                )
            else:
                raise GitError(f"{remote_ref} has diverged from {source}; refusing publication rewrite")
        else:
            if not _is_ancestor(entry.path, remote_tip, old_tip):
                raise GitError(f"{remote_ref} has diverged from {source}; refusing publication rewrite")
            base_sha = remote_tip
            published_ids = set(published.task_ids)
            new_task_ids = [task_id for task_id in task_ids if task_id not in published_ids]
            if published_ids - set(task_ids):
                raise GitError("published feature history contains a task no longer owned by the feature")
            if not new_task_ids:
                return validate_feature_publication(
                    feature_id,
                    source_root=entry.path,
                    source_ref=source,
                    base_ref=entry.base_sha,
                    expected_task_ids=task_ids,
                )
    else:
        base_sha = entry.base_sha
        new_task_ids = list(task_ids)

    task_commits = [_task_deliverable_commit(entry.path, task_id) for task_id in new_task_ids]
    new_tip = _build_publication_tail(
        entry.path,
        base_sha=base_sha,
        final_tree_ref=old_tip,
        task_ids=new_task_ids,
        task_commits=task_commits,
    )
    _git(entry.path, "update-ref", f"refs/heads/{source}", new_tip, old_tip)
    history = validate_feature_publication(
        feature_id,
        source_root=entry.path,
        source_ref=source,
        base_ref=entry.base_sha,
        expected_task_ids=task_ids,
    )
    if remote_lease_sha is None:
        return history
    return PublicationHistory(
        base_sha=history.base_sha,
        tip_sha=history.tip_sha,
        task_ids=history.task_ids,
        commits=history.commits,
        remote_lease_sha=remote_lease_sha,
    )


def validate_feature_publication(
    feature_id: str,
    *,
    source_root: Path,
    source_ref: str,
    base_ref: str,
    expected_task_ids: list[str] | None,
) -> PublicationHistory:
    """Fail closed unless the publication range is one deliverable commit per Task."""

    root = Path(source_root).resolve()
    _require_clean(root)
    merge_base = _git(root, "merge-base", base_ref, source_ref, check=False)
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        raise GitError(f"{source_ref} has no merge base with {base_ref}")
    base_sha = merge_base.stdout.strip()
    commits = tuple(
        line
        for line in _git(root, "rev-list", "--reverse", f"{base_sha}..{source_ref}").stdout.splitlines()
        if line
    )
    trailer_ids: list[str] = []
    for sha in commits:
        parents = _git(root, "show", "-s", "--format=%P", sha).stdout.split()
        if len(parents) != 1:
            raise GitError(f"feature publication contains merge commit {sha[:12]}")
        task_ids = _task_trailers(_git(root, "show", "-s", "--format=%B", sha).stdout)
        if len(task_ids) != 1:
            raise GitError(f"feature publication commit {sha[:12]} needs exactly one Cascade-Task trailer")
        paths = [
            path
            for path in _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha).stdout.splitlines()
            if path
        ]
        if not paths or all(path.startswith(_LIFECYCLE_PREFIXES) for path in paths):
            raise GitError(f"feature publication commit {sha[:12]} is lifecycle-only")
        trailer_ids.append(task_ids[0])
    if len(set(trailer_ids)) != len(trailer_ids):
        raise GitError("feature publication repeats a Cascade-Task trailer")
    if expected_task_ids is not None and set(trailer_ids) != set(expected_task_ids):
        raise GitError(
            "feature publication task mismatch: "
            f"expected {sorted(expected_task_ids)}, found {sorted(trailer_ids)}"
        )
    return PublicationHistory(
        base_sha=base_sha,
        tip_sha=_git(root, "rev-parse", source_ref).stdout.strip(),
        task_ids=tuple(trailer_ids),
        commits=commits,
    )


def _completed_task_ids(feature_id: str, feature_root: Path) -> list[str]:
    board = list_board(feature_root)
    try:
        feature = read_doc(feature_id, root=feature_root)
    except NotFound as exc:
        raise GitError(f"feature plan missing: {feature_id}") from exc
    ids = list(feature.meta.children)
    for task_id, meta in board.by_id.items():
        if meta.tier == "task" and meta.parent == feature_id and task_id not in ids:
            ids.append(task_id)
    for task_id in ids:
        meta = board.by_id.get(task_id)
        if meta is None or meta.status != "completed" or meta.path.parent.name != "3_completed":
            raise GitError(f"feature publication requires completed child {task_id}")
    return ids


def _task_deliverable_commit(root: Path, task_id: str) -> str:
    branch = integration_branch("task", task_id)
    candidates: list[str] = []
    result = _git(root, "rev-list", branch, check=False)
    if result.returncode != 0:
        raise GitError(f"task branch missing: {branch}")
    for sha in result.stdout.splitlines():
        body = _git(root, "show", "-s", "--format=%B", sha).stdout
        if _task_trailers(body) == [task_id]:
            candidates.append(sha)
    if len(candidates) != 1:
        raise GitError(
            f"{branch} must contain exactly one commit with Cascade-Task: {task_id}; "
            f"found {len(candidates)}"
        )
    return candidates[0]


def _build_publication_tail(
    root: Path,
    *,
    base_sha: str,
    final_tree_ref: str,
    task_ids: list[str],
    task_commits: list[str],
) -> str:
    with tempfile.TemporaryDirectory(prefix="cascade-publish-") as tmp:
        index = str(Path(tmp) / "index")
        env = {**os.environ, "GIT_INDEX_FILE": index}
        _git_env(root, env, "read-tree", base_sha)
        parent = base_sha
        for position, (task_id, source_sha) in enumerate(zip(task_ids, task_commits, strict=True)):
            if position == len(task_ids) - 1:
                _git_env(root, env, "read-tree", final_tree_ref)
            else:
                source_parent = _git(root, "show", "-s", "--format=%P", source_sha).stdout.split()
                if len(source_parent) != 1:
                    raise GitError(f"task deliverable {source_sha[:12]} is not linear")
                patch = subprocess.run(
                    ["git", "diff", "--binary", source_parent[0], source_sha],
                    cwd=root,
                    capture_output=True,
                )
                if patch.returncode != 0:
                    raise GitError("could not read task deliverable patch")
                applied = subprocess.run(
                    ["git", "apply", "--cached", "--3way", "-"],
                    cwd=root,
                    env=env,
                    input=patch.stdout,
                    capture_output=True,
                )
                if applied.returncode != 0:
                    # Concurrent Tasks may edit the same lines. The integration
                    # merge already contains the reviewed resolution, so use
                    # its tree instead of trying to resolve the patch again.
                    snapshot = _integration_merge_snapshot(
                        root, source_sha, final_tree_ref, task_commits[position + 1 :]
                    )
                    if snapshot is None:
                        raise GitError(
                            applied.stderr.decode(errors="replace").strip()
                            or f"could not fold {task_id} into publication history"
                        )
                    _git_env(root, env, "read-tree", "--reset", snapshot)
            tree = _git_env(root, env, "write-tree").stdout.strip()
            title = read_doc(task_id, root=root).meta.title
            message = f"task/{task_id}: {title}\n\n{_TRAILER} {task_id}\n"
            parent = _git_env(root, env, "commit-tree", tree, "-p", parent, "-m", message).stdout.strip()
        return parent


def _integration_merge_snapshot(
    root: Path,
    source_sha: str,
    final_ref: str,
    later_task_commits: list[str],
) -> str | None:
    """Find the merge that integrated a Task before any later Task landed."""

    merges = _git(root, "rev-list", "--merges", "--reverse", final_ref).stdout.splitlines()
    for merge_sha in merges:
        parents = _git(root, "show", "-s", "--format=%P", merge_sha).stdout.split()
        if len(parents) != 2:
            continue
        source_in_parents = [_is_ancestor(root, source_sha, parent) for parent in parents]
        if source_in_parents.count(True) != 1:
            continue
        if any(_is_ancestor(root, later_sha, merge_sha) for later_sha in later_task_commits):
            return None
        return merge_sha
    return None


def _task_trailers(message: str) -> list[str]:
    return [line.removeprefix(_TRAILER).strip() for line in message.splitlines() if line.startswith(_TRAILER)]


def _require_clean(root: Path) -> None:
    dirty = _git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if dirty:
        raise GitError("feature worktree has tracked changes; refusing publication rewrite")


def _optional_ref(root: Path, ref: str) -> str | None:
    result = _git(root, "show-ref", "--verify", "--hash", ref, check=False)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _recovery_ref(feature_id: str) -> str:
    return f"refs/cascade/publication-recovery/{feature_id}"


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return _git(root, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


def _range_task_trailers(root: Path, base_ref: str, tip_ref: str) -> list[str]:
    merge_base = _git(root, "merge-base", base_ref, tip_ref, check=False)
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        return []
    trailers: list[str] = []
    for sha in _git(root, "rev-list", f"{merge_base.stdout.strip()}..{tip_ref}").stdout.splitlines():
        trailers.extend(_task_trailers(_git(root, "show", "-s", "--format=%B", sha).stdout))
    return trailers


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} failed")
    return result


def _git_env(
    root: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} failed")
    return result
