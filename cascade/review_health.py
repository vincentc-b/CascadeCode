"""Proactive health admission for open Feature and Epic reviews."""

from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cascade.board.errors import GitError
from cascade.resolution_actions import (
    admit_resolution_action,
    normalize_epic_031_recovery_request,
)
from cascade.task.action_recovery import capture_and_route_action_failure
from cascade.team_review_recovery import (
    local_review_resolution_ready,
    publish_team_review_resolution,
)
from cascade.tracking import MergeRequest, detect_forge, merge_request_snapshot
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    locate_trunk,
    merged_board,
)


def _review_records(trunk: Path) -> dict[str, dict[str, object]]:
    try:
        raw = json.loads(
            (trunk / ".cascade" / "reviews.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return (
        {
            str(key): dict(value)
            for key, value in raw.items()
            if isinstance(value, Mapping)
        }
        if isinstance(raw, Mapping)
        else {}
    )


def _git(worktree: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=worktree, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _is_ancestor(worktree: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=worktree,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).returncode
        == 0
    )


def _fetch_review_heads(
    worktree: Path, source_ref: str, target_ref: str
) -> tuple[str, str] | None:
    source_remote = f"refs/remotes/origin/{source_ref}"
    target_remote = f"refs/remotes/origin/{target_ref}"
    fetched = subprocess.run(
        [
            "git",
            "fetch",
            "--no-tags",
            "origin",
            f"refs/heads/{source_ref}:{source_remote}",
            f"refs/heads/{target_ref}:{target_remote}",
        ],
        cwd=worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if fetched.returncode != 0:
        return None
    source_sha = _git(worktree, "rev-parse", "--verify", f"{source_remote}^{{commit}}")
    target_sha = _git(worktree, "rev-parse", "--verify", f"{target_remote}^{{commit}}")
    return (source_sha, target_sha) if source_sha and target_sha else None


def reconcile_open_review_health(
    root: Path, *, owner_id: str | None = None
) -> list[dict[str, object]]:
    """Admit each conflicting open review and route or publish it exactly once."""

    trunk = locate_trunk(root)
    forge = detect_forge(trunk)
    if forge is None:
        return []
    board = merged_board(trunk)
    results: list[dict[str, object]] = []
    records = _review_records(trunk)
    if owner_id is not None:
        records = {owner_id: records[owner_id]} if owner_id in records else {}
    for owner_id, record in sorted(records.items()):
        if (
            record.get("stage") == "completed"
            or str(record.get("state") or record.get("forge_state") or "").lower()
            == "merged"
        ):
            _reconcile_completed_review(owner_id, trunk)
            continue
        if record.get("closed"):
            continue
        state = str(record.get("state") or record.get("forge_state") or "open").lower()
        if state in {"closed", "merged"} or record.get("stage") == "completed":
            continue
        source_ref = str(record.get("source_branch") or "").strip()
        target_ref = str(record.get("target_branch") or "").strip()
        url = str(record.get("url") or record.get("review_url") or "").strip()
        owner = board.by_id.get(owner_id)
        if (
            not source_ref
            or not target_ref
            or not url
            or owner is None
            or owner.tier not in {"feature", "epic"}
        ):
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
            results.append(
                _health_wait(owner_id, "transient_outage", "review_snapshot_failed")
            )
            continue
        if snapshot.get("state") == "merged":
            _reconcile_completed_review(owner_id, trunk)
            results.append({"owner_id": owner_id, "outcome": "completed"})
            continue
        health = snapshot.get("review_health")
        if isinstance(health, Mapping):
            health_state = str(health.get("state") or "transient_outage")
            health_reason = str(health.get("reason") or health_state)
            if health_state == "green":
                _reconcile_completed_review(
                    owner_id, trunk, reason="review_health_restored"
                )
                results.append({"owner_id": owner_id, "outcome": "healthy"})
                continue
            if health_state == "terminal":
                results.append(_health_wait(owner_id, health_state, health_reason))
                continue
            if health_state in {"failed", "actionable_human_feedback"} or (
                health_state == "conflict_or_moving_target"
                and health_reason == "merge_conflict"
            ):
                results.append(
                    _route_actionable_review_health(
                        trunk,
                        owner,
                        record,
                        snapshot,
                        health,
                        forge=forge,
                    )
                )
                continue
            results.append(_health_wait(owner_id, health_state, health_reason, health))
            continue
        if snapshot.get("state") == "open" and snapshot.get("mergeability") in {
            "mergeable",
            "clean",
        }:
            _reconcile_completed_review(
                owner_id, trunk, reason="review_health_restored"
            )
            results.append({"owner_id": owner_id, "outcome": "healthy"})
            continue
        if snapshot.get("state") == "open" and snapshot.get("mergeability") not in {
            "conflicting",
            "mergeable",
            "clean",
        }:
            results.append(
                _route_health_failure(trunk, owner, record, "mergeability_unknown")
            )
        if (
            snapshot.get("state") != "open"
            or snapshot.get("mergeability") != "conflicting"
        ):
            continue
        entry = get_integration_worktree(trunk, owner.tier, owner_id)
        if entry is None or not entry.path.is_dir():
            results.append(
                _route_health_failure(trunk, owner, record, "owned_worktree_missing")
            )
            continue
        heads = _fetch_review_heads(entry.path, source_ref, target_ref)
        if heads is None:
            results.append(
                _route_health_failure(trunk, owner, record, "review_fetch_failed")
            )
            continue
        source_sha, target_sha = heads
        # Forge mergeability may lag immediately after a successful publication.
        if _is_ancestor(entry.path, target_sha, source_sha):
            _reconcile_completed_review(
                owner_id, trunk, reason="review_target_integrated"
            )
            results.append({"owner_id": owner_id, "outcome": "healthy"})
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
            blocker = admission.action.get("blocker") or {}
            failure = _route_health_failure(
                trunk,
                owner,
                record,
                str(blocker.get("code") or "review_admission_refused"),
                blocker,
            )
            results.append(
                {
                    **failure,
                    "outcome": "blocked",
                    "admission_id": admission.action_id,
                    "blocker": blocker,
                }
            )
            continue
        _reconcile_completed_review(
            owner_id,
            trunk,
            reason="review_recovery_admitted",
            health_only=True,
            successor=admission.action_id,
        )
        if (
            local_review_resolution_ready(
                admission.action_id, team_kind=team_kind, team_id=owner_id, root=trunk
            )
            and _git(entry.path, "rev-parse", "HEAD") != source_sha
        ):
            published = publish_team_review_resolution(
                admission.action_id, team_kind=team_kind, team_id=owner_id, root=trunk
            )
            results.append(
                {
                    "owner_id": owner_id,
                    "action_id": admission.action_id,
                    "outcome": "published"
                    if published.get("recovery_state") == "completed"
                    else "blocked",
                }
            )
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
        results.append(
            {
                "owner_id": owner_id,
                "action_id": admission.action_id,
                "outcome": "routed",
            }
        )
    return results


def _health_wait(
    owner_id: str,
    wait_type: str,
    reason: str,
    health: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Project a non-actionable observation without creating recovery work."""

    result: dict[str, object] = {
        "owner_id": owner_id,
        "outcome": "waiting",
        "wait_type": wait_type,
        "reason": reason,
    }
    checks = health.get("checks") if isinstance(health, Mapping) else None
    if isinstance(checks, list):
        result["checks"] = [str(check) for check in checks]
    return result


def _json_identity(value: object) -> object:
    """Return deterministic JSON evidence while discarding incidental ordering."""

    if isinstance(value, Mapping):
        return {
            str(key): _json_identity(item)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, list):
        normalized = [_json_identity(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _actionable_evidence_identity(
    record: Mapping[str, object],
    snapshot: Mapping[str, object],
    health: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    """Bind repair identity to the original review and material blocker facts."""

    state = str(health.get("state") or "")
    blocker: object
    if state == "failed":
        results = snapshot.get("required_check_results")
        checks = results.get("checks") if isinstance(results, Mapping) else None
        names = health.get("checks") if isinstance(health.get("checks"), list) else []
        blocker = {
            "checks": {
                str(name): _json_identity(checks.get(name))
                for name in sorted(str(name) for name in names)
            }
            if isinstance(checks, Mapping)
            else sorted(str(name) for name in names),
            "result_generation": results.get("generation")
            if isinstance(results, Mapping)
            else None,
            "policy": _json_identity(snapshot.get("required_check_policy")),
        }
    elif state == "actionable_human_feedback":
        feedback = snapshot.get("review_feedback")
        if isinstance(feedback, Mapping):
            blocker = _json_identity(
                feedback.get("actionable_feedback")
                or feedback.get("actionable_reviewers")
                or feedback
            )
        else:
            blocker = []
    else:
        blocker = {"reason": health.get("reason") or "merge_conflict"}
    evidence: dict[str, object] = {
        "review": {
            "url": record.get("url") or record.get("review_url"),
            "number": record.get("number"),
            "source_ref": record.get("source_branch"),
            "target_ref": record.get("target_branch"),
        },
        "source_head": snapshot.get("source_revision") or record.get("source_head"),
        "target_head": snapshot.get("target_revision") or record.get("target_head"),
        "health_state": state,
        "blocker": blocker,
    }
    digest = hashlib.sha256(
        json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    return digest, evidence


def _blocker_identity(evidence: Mapping[str, object]) -> str:
    """Identify the upstream obligation independently of its run generation."""

    blocker = evidence.get("blocker")
    if evidence.get("health_state") == "failed" and isinstance(blocker, Mapping):
        checks = blocker.get("checks")
        blocker = {
            "checks": sorted(str(name) for name in checks)
            if isinstance(checks, Mapping)
            else _json_identity(checks)
        }
    identity = {
        "review": evidence.get("review"),
        "health_state": evidence.get("health_state"),
        "blocker": blocker,
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _record_downstream_review_fence(
    root: Path,
    feature_id: str,
    *,
    evidence: Mapping[str, object],
    evidence_generation: str,
    repair_action_id: object,
    repair_generation: object,
) -> None:
    """Publish one normalized upstream observation to existing Task actions."""

    from cascade.task_rollup import record_upstream_review_observation

    record_upstream_review_observation(
        feature_id,
        blocker_identity=_blocker_identity(evidence),
        evidence_generation=evidence_generation,
        repair_action_id=(repair_action_id if isinstance(repair_action_id, str) else None),
        repair_generation=(repair_generation if type(repair_generation) is int else None),
        root=root,
    )


def _existing_repair_identity(
    feature_id: str, core_identity: str, *, root: Path
) -> tuple[str, str, int, str] | None:
    from cascade.feature.repair import feature_repair_actions

    for action in sorted(
        feature_repair_actions(feature_id, root=root),
        key=lambda row: int(row.get("generation") or 0),
        reverse=True,
    ):
        evidence = action.get("request_evidence")
        health = (
            evidence.get("review_health") if isinstance(evidence, Mapping) else None
        )
        if isinstance(health, Mapping) and health.get("core_identity") == core_identity:
            request_id = action.get("request_id")
            material_identity = health.get("material_identity")
            generation = action.get("generation")
            action_id = action.get("action_id")
            if (
                isinstance(request_id, str)
                and isinstance(action_id, str)
                and isinstance(material_identity, str)
                and type(generation) is int
            ):
                return action_id, request_id, generation, material_identity
    return None


def _route_actionable_review_health(
    root: Path,
    owner: Any,
    record: Mapping[str, object],
    snapshot: Mapping[str, object],
    health: Mapping[str, object],
    *,
    forge: str,
) -> dict[str, object]:
    """Join actionable evidence to one generation-bound Feature repair writer."""

    if owner.tier != "feature" or not owner.parent:
        return _health_wait(
            owner.id, "owner_unavailable", "feature_repair_owner_missing"
        )

    from cascade.feature.repair import feature_repair_actions
    from cascade.team_supervision import request_feature_review_repair

    core_identity, evidence = _actionable_evidence_identity(record, snapshot, health)
    existing = _existing_repair_identity(owner.id, core_identity, root=root)
    if existing is not None:
        action_id, _request_id, repair_generation, material_identity = existing
        _record_downstream_review_fence(
            root,
            owner.id,
            evidence=evidence,
            evidence_generation=core_identity,
            repair_action_id=action_id,
            repair_generation=repair_generation,
        )
        return {
            "owner_id": owner.id,
            "action_id": action_id,
            "repair_generation": repair_generation,
            "material_identity": material_identity,
            "outcome": "waiting",
            "wait_type": "repair_generation_reused",
            "reason": health.get("reason") or health.get("state"),
            "replayed": True,
        }

    repair_generation = 1 + max(
        (
            int(action.get("generation") or 0)
            for action in feature_repair_actions(owner.id, root=root)
        ),
        default=0,
    )
    material_identity = hashlib.sha256(
        f"{core_identity}\0{repair_generation}".encode()
    ).hexdigest()
    request_id = f"review-health:{material_identity[:24]}"

    source_head = snapshot.get("source_revision") or record.get("source_head")
    target_head = snapshot.get("target_revision") or record.get("target_head")
    review_forge = record.get("forge") or forge
    if not all(
        isinstance(value, str) and value.strip()
        for value in (source_head, target_head, review_forge)
    ):
        return _health_wait(
            owner.id, "evidence_unavailable", "review_heads_unavailable"
        )
    observed_generation = (
        record.get("current_generation") or record.get("generation") or 0
    )
    if isinstance(observed_generation, bool):
        return _health_wait(
            owner.id, "evidence_unavailable", "review_generation_unavailable"
        )
    try:
        observed_generation = int(observed_generation)
    except (TypeError, ValueError):
        return _health_wait(
            owner.id, "evidence_unavailable", "review_generation_unavailable"
        )

    repair_evidence = {
        "review_health": {
            "core_identity": core_identity,
            "blocker_identity": _blocker_identity(evidence),
            "material_identity": material_identity,
            "repair_generation": repair_generation,
            "observation": evidence,
        }
    }
    try:
        routed = request_feature_review_repair(
            owner.id,
            request_id,
            root=root,
            requesting_parent_id=str(owner.parent),
            reason=str(
                health.get("reason") or health.get("state") or "review_unhealthy"
            ),
            evidence=repair_evidence,
            approval_reference=f"review-health:{material_identity}",
            scope_reference=f"review-health:{material_identity}",
            review_url=str(record.get("url") or record.get("review_url")),
            review_forge=str(review_forge),
            source_ref=str(record.get("source_branch")),
            target_ref=str(record.get("target_branch")),
            observed_source_head=str(source_head),
            observed_target_head=str(target_head),
            observed_review_generation=observed_generation,
        )
    except (OSError, PermissionError, ValueError):
        _record_downstream_review_fence(
            root,
            owner.id,
            evidence=evidence,
            evidence_generation=core_identity,
            repair_action_id=None,
            repair_generation=None,
        )
        return _health_wait(
            owner.id, "repair_admission_unavailable", "repair_admission_failed"
        )
    _record_downstream_review_fence(
        root,
        owner.id,
        evidence=evidence,
        evidence_generation=core_identity,
        repair_action_id=routed.get("action_id"),
        repair_generation=routed.get("generation"),
    )
    return {
        "owner_id": owner.id,
        "action_id": routed.get("action_id"),
        "repair_generation": routed.get("generation"),
        "material_identity": material_identity,
        "outcome": "routed" if routed.get("admitted") else "waiting",
        "wait_type": None
        if routed.get("admitted")
        else routed.get("blocker")
        or routed.get("next_prerequisite")
        or "repair_generation_pending",
        "reason": health.get("reason") or health.get("state"),
        "replayed": bool(routed.get("replayed")),
    }


def _route_health_failure(root, owner, record, code, blocker=None):
    from hashlib import sha256
    from cascade.task.lifecycle_lock import task_lifecycle_lock
    from cascade.task.action_recovery import load_action

    identity_fields = {
        key: record.get(key)
        for key in ("url", "review_url", "number", "source_branch", "target_branch")
    }
    identity = sha256(
        json.dumps(identity_fields, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    with task_lifecycle_lock(root=root):
        base_id = f"{owner.id}:review-health:{code}:{identity}"
        action_id = base_id
        generation = 1
        while (
            previous := load_action(action_id, root=root)
        ) is not None and previous.get("recovery_state") == "completed":
            generation += 1
            action_id = f"{base_id}:{generation}"
        return _capture_health_failure(root, owner, record, code, action_id, blocker)


def _capture_health_failure(root, owner, record, code, action_id, blocker=None):
    capture_and_route_action_failure(
        action_id,
        "review_health",
        affected_work_id=owner.id,
        intended_target_ref=record.get("target_branch"),
        root=root,
        failure_code=code,
        safe_summary=(
            f"Review health requires attention: {code}. "
            f"Call publish_review_resolution with action_id {action_id} to recheck this owned review "
            "and admit recovery against its current heads. Restore the owned checkout if missing; "
            "resolve fetch/authentication failures before retrying. No publication is authorized until admission succeeds."
        ),
        evidence={
            "review_url": record.get("url") or record.get("review_url"),
            "source_ref": record.get("source_branch"),
            "recovery_tool": "publish_review_resolution",
            "admission_blocker": blocker,
        },
        owning_team={"kind": f"{owner.tier}_team", "work_id": owner.id},
    )
    return {
        "owner_id": owner.id,
        "action_id": action_id,
        "outcome": "routed",
        "reason": code,
    }


def _reconcile_completed_review(
    work_id: str,
    root: Path,
    *,
    reason: str = "canonical_review_completed",
    health_only: bool = False,
    successor: str | None = None,
) -> None:
    """The canonical closed review supersedes earlier failed repair attempts."""
    from cascade.task.action_recovery import (
        _read_payload,
        _write_payload,
        _actions,
        _iso,
    )
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    with task_lifecycle_lock(root=root):
        payload = _read_payload(root)
        actions = _actions(payload)
        changed = False
        for action in actions.values():
            if action.get("action_kind") not in (
                {"review_health"} if health_only else {"review_health", "review_rebase"}
            ):
                continue
            evidence = (action.get("recovery") or {}).get("evidence") or {}
            if (
                evidence.get("affected_work_id") == work_id
                and action.get("recovery_state") != "completed"
            ):
                action["recovery_state"] = "completed"
                action["completion_reconciliation"] = {
                    "reason": reason,
                    "at": _iso(None),
                    "successor_action_id": successor,
                }
                action["updated_at"] = _iso(None)
                changed = True
        if changed:
            payload["actions"] = actions
            _write_payload(root, payload)


def retry_review_health(
    action_id: str, *, team_kind: str, team_id: str, root: Path
) -> dict[str, object]:
    """An owned health inquiry can re-enter admission, never bypass it."""
    from cascade.task.action_recovery import load_action

    action = load_action(action_id, root=root)
    if action is None or action.get("action_kind") != "review_health":
        raise PermissionError("not a review-health action")
    if (action.get("recovery") or {}).get("owning_team") != {
        "kind": team_kind,
        "work_id": team_id,
    }:
        raise PermissionError("review recovery belongs to a different team")
    # Recheck even a previously resolved incident: remote facts may have moved.
    outcomes = reconcile_open_review_health(root, owner_id=team_id)
    current = load_action(action_id, root=root)
    return {
        "action_id": action_id,
        "recovery_state": current.get("recovery_state"),
        "outcomes": outcomes,
        "reason": None if outcomes else "review_record_or_forge_unavailable",
    }
