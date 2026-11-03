"""Epic Team recovery for accepted stacked reviews stranded off the Epic line."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from cascade.board.errors import GitError
from cascade.epic.registry import register_epic_tool
from cascade.review import (
    _ensure_opened_toast,
    find_merge_request,
    persist_stacked_reconciliation_review,
)
from cascade.task.action_recovery import (
    ActionNotFound,
    load_action,
    record_owner_resolution,
    replace_action_metadata,
)
from cascade.tracking import MergeRequest, create_merge_request
from cascade.watchdog.lock import process_lock
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    locate_trunk,
)


_ACTION_KIND = "stacked_review_integration_gap"


def reconcile_stacked_review_gap(
    action_id: str, *, epic_id: str, root: Path
) -> dict[str, object]:
    """Create or reuse the Epic-targeted review requested by one gap action.

    The recovery action is the stable idempotency record.  The Epic Team may
    retry this tool freely: the same source/target review is found before a
    creation is attempted, and the action keeps the review identity and the
    accepted predecessor review that originated it.
    """

    trunk = locate_trunk(root)
    # The forge lookup/create and registry replacement must be one Cascade
    # critical section.  This prevents two duplicate callbacks from both
    # deciding that no follow-up exists.
    with process_lock:
        action = load_action(action_id, root=trunk)
        if action is None:
            raise ActionNotFound(action_id)
        evidence, decision_id = _gap_evidence(action, epic_id=epic_id)
        existing = _reconciliation_from_metadata(action, evidence)
        if existing is None:
            mr = _find_or_create_review(evidence, root=trunk)
            action = _record_reconciliation(action, evidence, mr, root=trunk)
        else:
            mr = existing

        record = persist_stacked_reconciliation_review(
            str(evidence["feature_id"]),
            mr,
            action_id=action_id,
            originating_review=dict(evidence["accepted_review"]),
            root=trunk,
        )
        _ensure_opened_toast(str(evidence["feature_id"]), mr, record, root=trunk)
        resolved = _resolve_gap_decision(
            action, decision_id, evidence, mr, root=trunk
        )
    return {
        "action_id": action_id,
        "feature_id": evidence["feature_id"],
        "epic_id": epic_id,
        "review_url": mr.url,
        "target_branch": mr.target_branch,
        "originating_review": dict(evidence["accepted_review"]),
        "recovery_state": resolved["recovery_state"],
    }


def _gap_evidence(action: dict[str, object], *, epic_id: str) -> tuple[dict[str, object], str]:
    if action.get("action_kind") != _ACTION_KIND:
        raise ValueError(f"{action.get('action_id')} is not a stacked review recovery action")
    stored = action.get("metadata")
    if not isinstance(stored, dict):
        raise ValueError("stacked review recovery is missing evidence")
    evidence = {
        key: stored[key]
        for key in (
            "feature_id",
            "epic_id",
            "predecessor_id",
            "expected_target_branch",
            "accepted_review",
        )
        if key in stored
    }
    if evidence.get("epic_id") != epic_id:
        raise ValueError(f"recovery action does not belong to {epic_id}")
    expected = f"epic/{epic_id}"
    if evidence.get("expected_target_branch") != expected:
        raise ValueError("stacked review recovery has an invalid Epic target")
    accepted = evidence.get("accepted_review")
    if not isinstance(accepted, dict):
        raise ValueError("stacked review recovery is missing accepted-review provenance")
    source = accepted.get("source_branch")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("accepted-review provenance is missing its source branch")
    decisions = action.get("owner_decisions")
    if not isinstance(decisions, list):
        raise ValueError("stacked review recovery is missing its Epic Team decision")
    decision = next(
        (
            row for row in decisions
            if isinstance(row, dict)
            and row.get("owner") == "epic_team"
            and row.get("metadata") == evidence
        ),
        None,
    )
    if not isinstance(decision, dict) or not isinstance(decision.get("decision_id"), str):
        raise ValueError("stacked review recovery is missing its Epic Team decision")
    return dict(evidence), decision["decision_id"]


def _find_or_create_review(evidence: dict[str, object], *, root: Path) -> MergeRequest:
    epic_id = str(evidence["epic_id"])
    entry = get_integration_worktree(root, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing: {epic_id}")
    source = str(dict(evidence["accepted_review"])["source_branch"])
    target = str(evidence["expected_target_branch"])
    existing = find_merge_request(entry.path, source_branch=source, target_branch=target)
    if existing is not None:
        return existing
    feature_id = str(evidence["feature_id"])
    original_url = str(dict(evidence["accepted_review"]).get("url") or "unknown review")
    return create_merge_request(
        entry.path,
        title=f"{feature_id}: reconcile accepted stacked review",
        body=(
            f"Reconciles accepted stacked review {original_url} into `{target}`. "
            "This follow-up is managed by the Epic Team."
        ),
        source_branch=source,
        target_branch=target,
        draft=False,
    )


def _reconciliation_from_metadata(
    action: dict[str, object], evidence: dict[str, object]
) -> MergeRequest | None:
    metadata = action.get("metadata")
    if not isinstance(metadata, dict):
        return None
    row = metadata.get("reconciliation_review")
    if not isinstance(row, dict):
        return None
    try:
        mr = MergeRequest(
            url=str(row["url"]),
            number=str(row["number"]) if row.get("number") is not None else None,
            forge=str(row["forge"]),  # type: ignore[arg-type]
            source_branch=str(row["source_branch"]),
            target_branch=str(row["target_branch"]),
            draft=bool(row.get("draft", False)),
        )
    except KeyError:
        return None
    if (
        mr.source_branch != dict(evidence["accepted_review"])["source_branch"]
        or mr.target_branch != evidence["expected_target_branch"]
    ):
        raise ValueError("stacked review recovery has conflicting reconciliation evidence")
    return mr


def _record_reconciliation(
    action: dict[str, object], evidence: dict[str, object], mr: MergeRequest, *, root: Path
) -> dict[str, object]:
    metadata = dict(evidence)
    metadata["reconciliation_review"] = {
        "url": mr.url,
        "number": mr.number,
        "forge": mr.forge,
        "source_branch": mr.source_branch,
        "target_branch": mr.target_branch,
        "draft": mr.draft,
    }
    return replace_action_metadata(str(action["action_id"]), metadata, root=root)


def _resolve_gap_decision(
    action: dict[str, object],
    decision_id: str,
    evidence: dict[str, object],
    mr: MergeRequest,
    *,
    root: Path,
) -> dict[str, object]:
    identity = json.dumps(
        {"action_id": action["action_id"], "target_branch": evidence["expected_target_branch"]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    resolution_id = f"stacked-review-reconciliation:{sha256(identity).hexdigest()}"
    metadata = {"review_url": mr.url, "target_branch": mr.target_branch}
    return record_owner_resolution(
        str(action["action_id"]), decision_id, resolution_id, root=root, metadata=metadata
    )


register_epic_tool("reconcile_stacked_review_gap", reconcile_stacked_review_gap)

