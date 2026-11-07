"""Proactive health admission for open Feature and Epic reviews."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Mapping

from cascade.board.errors import GitError
from cascade.resolution_actions import admit_resolution_action, normalize_epic_031_recovery_request
from cascade.task.action_recovery import capture_and_route_action_failure
from cascade.team_review_recovery import local_review_resolution_ready, publish_team_review_resolution
from cascade.tracking import MergeRequest, detect_forge, merge_request_snapshot
from cascade.workspace.integration_worktree import get_integration_worktree, locate_trunk, merged_board


def _review_records(trunk: Path) -> dict[str, dict[str, object]]:
    try:
        raw = json.loads((trunk / ".cascade" / "reviews.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): dict(value) for key, value in raw.items() if isinstance(value, Mapping)} if isinstance(raw, Mapping) else {}


def _git(worktree: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=worktree, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _is_ancestor(worktree: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    ).returncode == 0


def _fetch_review_heads(worktree: Path, source_ref: str, target_ref: str) -> tuple[str, str] | None:
    source_remote = f"refs/remotes/origin/{source_ref}"
    target_remote = f"refs/remotes/origin/{target_ref}"
    fetched = subprocess.run(
        [
            "git", "fetch", "--no-tags", "origin",
            f"refs/heads/{source_ref}:{source_remote}",
            f"refs/heads/{target_ref}:{target_remote}",
        ],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    )
    if fetched.returncode != 0:
        return None
    source_sha = _git(worktree, "rev-parse", "--verify", f"{source_remote}^{{commit}}")
    target_sha = _git(worktree, "rev-parse", "--verify", f"{target_remote}^{{commit}}")
    return (source_sha, target_sha) if source_sha and target_sha else None


def reconcile_open_review_health(root: Path) -> list[dict[str, object]]:
    """Admit each conflicting open review and route or publish it exactly once."""

    trunk = locate_trunk(root)
    forge = detect_forge(trunk)
    if forge is None:
        return []
    board = merged_board(trunk)
    results: list[dict[str, object]] = []
    for owner_id, record in sorted(_review_records(trunk).items()):
        if record.get("closed"):
            continue
        state = str(record.get("state") or record.get("forge_state") or "open").lower()
        if state in {"closed", "merged"} or record.get("stage") == "completed":
            continue
        source_ref = str(record.get("source_branch") or "").strip()
        target_ref = str(record.get("target_branch") or "").strip()
        url = str(record.get("url") or record.get("review_url") or "").strip()
        owner = board.by_id.get(owner_id)
        if not source_ref or not target_ref or not url or owner is None or owner.tier not in {"feature", "epic"}:
            continue
        review = MergeRequest(
            url=url,
            number=str(record.get("number") or "") or None,
            forge=forge,
            source_branch=source_ref,
            target_branch=target_ref,
            draft=bool(record.get("draft", False)),
        )
        try:
            snapshot = merge_request_snapshot(trunk, review)
        except (GitError, OSError, ValueError):
            continue
        if snapshot.get("state") != "open" or snapshot.get("mergeability") != "conflicting":
            continue
        entry = get_integration_worktree(trunk, owner.tier, owner_id)
        if entry is None or not entry.path.is_dir():
            continue
        heads = _fetch_review_heads(entry.path, source_ref, target_ref)
        if heads is None:
            continue
        source_sha, target_sha = heads
        # Forge mergeability may lag immediately after a successful publication.
        if _is_ancestor(entry.path, target_sha, source_sha):
            continue
        team_kind = "epic_team" if owner.tier == "epic" else "feature_team"
        review_id = str(record.get("number") or url.rstrip("/").rsplit("/", 1)[-1])
        request = normalize_epic_031_recovery_request(
            {
                "review": {
                    "id": review_id,
                    "url": url,
                    "source_branch": source_ref,
                    "target_branch": target_ref,
                    "state": "open",
                },
                "source_sha": source_sha,
                "target_sha": target_sha,
                "actor": "supervisor:review_health",
                "assignment": {"owner": f"{owner.tier}:{owner_id}"},
            }
        )
        admission = admit_resolution_action(request, root=trunk)
        if admission.action.get("status") != "mutation_ready":
            results.append({"owner_id": owner_id, "action_id": admission.action_id, "outcome": "blocked"})
            continue
        if local_review_resolution_ready(
            admission.action_id, team_kind=team_kind, team_id=owner_id, root=trunk
        ) and _git(entry.path, "rev-parse", "HEAD") != source_sha:
            published = publish_team_review_resolution(
                admission.action_id, team_kind=team_kind, team_id=owner_id, root=trunk
            )
            results.append({
                "owner_id": owner_id,
                "action_id": admission.action_id,
                "outcome": "published" if published.get("recovery_state") == "completed" else "blocked",
            })
            continue
        capture_and_route_action_failure(
            admission.action_id,
            "review_rebase",
            affected_work_id=owner_id,
            intended_target_ref=target_ref,
            root=trunk,
            failure_code="review_conflict",
            safe_summary=(
                f"Open review {url} conflicts with {target_ref}. Resolve it in the owned "
                "worktree, run the relevant checks, then call publish_review_resolution "
                f"with action_id {admission.action_id}."
            ),
            evidence={
                "review_id": review_id,
                "review_url": url,
                "source_ref": source_ref,
                "target_ref": target_ref,
                "source_sha": source_sha,
                "target_sha": target_sha,
            },
            owning_team={"kind": team_kind, "work_id": owner_id},
        )
        results.append({"owner_id": owner_id, "action_id": admission.action_id, "outcome": "routed"})
    return results
