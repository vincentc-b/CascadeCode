"""Stacked feature dispatch: base selection, durable state, and completion gates (feat_007_001)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cascade.board.types import BoardIndex, WorkMeta
from cascade.war_room.room_settings import effective_stacked_pr_enabled
from cascade.workspace.integration_worktree import (
    integration_branch,
    locate_trunk,
    merged_board,
)
from cascade.watchdog.lock import process_lock


@dataclass(frozen=True)
class FeatureDispatchSelection:
    feature_id: str
    base_branch: str
    predecessor_id: str | None


@dataclass(frozen=True)
class FeatureDispatchPlan:
    ok: bool
    reason: str | None = None
    selection: FeatureDispatchSelection | None = None


def _state_path(trunk: Path) -> Path:
    return trunk / ".cascade" / "feature_dispatch.json"


def _load(trunk: Path) -> dict[str, dict[str, object]]:
    path = _state_path(trunk)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    features = raw.get("features")
    if not isinstance(features, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for key, value in features.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = dict(value)
    return out


def _save(trunk: Path, features: dict[str, dict[str, object]]) -> None:
    path = _state_path(trunk)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"features": features}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read_feature_dispatch_selection(
    feature_id: str, *, root: Path
) -> FeatureDispatchSelection | None:
    trunk = locate_trunk(root)
    record = _load(trunk).get(feature_id)
    if not record:
        return None
    base = str(record.get("base_branch") or "").strip()
    if not base:
        return None
    predecessor = record.get("predecessor_id")
    pred_id = str(predecessor).strip() if isinstance(predecessor, str) and predecessor else None
    return FeatureDispatchSelection(
        feature_id=feature_id,
        base_branch=base,
        predecessor_id=pred_id,
    )


def persist_feature_dispatch_selection(
    selection: FeatureDispatchSelection, *, root: Path
) -> None:
    trunk = locate_trunk(root)
    with process_lock:
        features = _load(trunk)
        features[selection.feature_id] = {
            "predecessor_id": selection.predecessor_id,
            "base_branch": selection.base_branch,
        }
        _save(trunk, features)


def feature_pull_request_linked(feature_id: str, *, root: Path) -> bool:
    from cascade.review import review_record_for_feature

    record = review_record_for_feature(feature_id, root=root)
    if record is None:
        return False
    url = str(record.get("url") or "").strip()
    return bool(url)


def refusal_if_feature_completion_without_pr(feature_id: str, *, root: Path) -> str | None:
    from cascade.review import review_enabled

    trunk = locate_trunk(root)
    if not review_enabled(trunk):
        return None
    if feature_pull_request_linked(feature_id, root=trunk):
        return None
    return "feature_pull_request_required"


def direct_feature_predecessors(meta: WorkMeta, board: BoardIndex) -> list[str]:
    preds: list[str] = []
    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is not None and dep.tier == "feature":
            preds.append(dep_id)
    return preds


def feature_dependency_ready(meta: WorkMeta, board: BoardIndex, *, root: Path) -> bool:
    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is None or dep.status != "completed" or dep.path.parent.name != "3_completed":
            return False
    return True


def epic_blocks_feature_dispatch(
    blocking_meta: WorkMeta,
    *,
    root: Path,
    epic_id: str,
    dispatching_feature_id: str | None = None,
    pending_review_ids: frozenset[str] | None = None,
) -> bool:
    """True when this sibling feature prevents another feature dispatch in the epic."""

    from cascade.review import feature_review_pending

    if blocking_meta.tier != "feature" or blocking_meta.parent != epic_id:
        return False
    if blocking_meta.path.parent.name == "2_active" and blocking_meta.status != "completed":
        return True
    pending = (
        blocking_meta.id in pending_review_ids
        if pending_review_ids is not None
        else feature_review_pending(blocking_meta.id, root=root)
    )
    if pending:
        candidate = dispatching_feature_id or blocking_meta.id
        return not effective_stacked_pr_enabled(candidate, epic_id, root=root)
    return False


def feature_merge_gated(
    meta: WorkMeta,
    board: BoardIndex,
    *,
    root: Path,
    pending_review_ids: frozenset[str] | None = None,
) -> bool:
    """True when merge-gated dispatch rules block this feature (stacked opt-in off)."""

    epic_id = meta.parent or ""
    if not epic_id:
        return True
    if effective_stacked_pr_enabled(meta.id, epic_id, root=root):
        return False
    if pending_review_ids is not None:
        if any(
            dep_id in pending_review_ids
            for dep_id in meta.depends_on
            if (dep := board.by_id.get(dep_id)) is not None and dep.tier == "feature"
        ):
            return True
        return any(
            feature.id in pending_review_ids
            for feature in board.by_id.values()
            if feature.tier == "feature" and feature.parent == epic_id
        )

    from cascade.review import epic_has_pending_feature_review, feature_review_pending

    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is not None and dep.tier == "feature" and feature_review_pending(
            dep_id, root=root
        ):
            return True
    return epic_has_pending_feature_review(epic_id, root=root)


def feature_dispatch_blocked_by_sibling(
    meta: WorkMeta,
    board: BoardIndex,
    *,
    root: Path,
    pending_review_ids: frozenset[str] | None = None,
) -> bool:
    epic_id = meta.parent or ""
    if not epic_id:
        return True
    for sibling in board.by_id.values():
        if sibling.id == meta.id:
            continue
        if epic_blocks_feature_dispatch(
            sibling,
            root=root,
            epic_id=epic_id,
            dispatching_feature_id=meta.id,
            pending_review_ids=pending_review_ids,
        ):
            return True
    return False


def plan_feature_dispatch(
    feature_id: str, meta: WorkMeta, board: BoardIndex, *, root: Path
) -> FeatureDispatchPlan:
    epic_id = meta.parent or ""
    if not epic_id:
        return FeatureDispatchPlan(ok=False, reason="bad_state")

    stacked = effective_stacked_pr_enabled(feature_id, epic_id, root=root)
    preds = direct_feature_predecessors(meta, board)
    if stacked and len(preds) > 1:
        return FeatureDispatchPlan(ok=False, reason="unsupported_topology")

    if not feature_dependency_ready(meta, board, root=root):
        return FeatureDispatchPlan(ok=False, reason="unmet_deps")

    epic_branch = integration_branch("epic", epic_id)
    predecessor_id: str | None = None
    base_branch = epic_branch

    if stacked and len(preds) == 1:
        pred_id = preds[0]
        stack_base = _stacked_predecessor_base(pred_id, board, root=root)
        if stack_base == "missing_predecessor_pr_identity":
            return FeatureDispatchPlan(
                ok=False, reason="missing_predecessor_pr_identity"
            )
        if stack_base is not None:
            predecessor_id = pred_id
            base_branch = stack_base

    return FeatureDispatchPlan(
        ok=True,
        selection=FeatureDispatchSelection(
            feature_id=feature_id,
            base_branch=base_branch,
            predecessor_id=predecessor_id,
        ),
    )


def ensure_feature_dispatch_selection(
    feature_id: str, meta: WorkMeta, board: BoardIndex, *, root: Path
) -> FeatureDispatchPlan:
    existing = read_feature_dispatch_selection(feature_id, root=root)
    if existing is not None:
        return FeatureDispatchPlan(ok=True, selection=existing)
    plan = plan_feature_dispatch(feature_id, meta, board, root=root)
    if plan.ok and plan.selection is not None:
        persist_feature_dispatch_selection(plan.selection, root=root)
    return plan


def review_target_branch(feature_id: str, epic_id: str, *, root: Path) -> str:
    selection = read_feature_dispatch_selection(feature_id, root=root)
    if selection is not None:
        return selection.base_branch
    return integration_branch("epic", epic_id)


def _stacked_predecessor_base(
    predecessor_id: str, board: BoardIndex, *, root: Path
) -> str | None:
    """Return epic base (None), predecessor branch name, or a failure reason token."""

    pred = board.by_id.get(predecessor_id)
    if pred is None:
        return "missing_predecessor_pr_identity"
    from cascade.review import review_enabled, review_record_for_feature

    record = review_record_for_feature(predecessor_id, root=root)
    if record is not None and record.get("closed"):
        return None
    if record is None:
        if not review_enabled(locate_trunk(root)):
            return None
        return "missing_predecessor_pr_identity"
    branch = str(record.get("source_branch") or "").strip()
    if not branch:
        return "missing_predecessor_pr_identity"
    return branch


def _predecessor_head_branch(predecessor_id: str, *, root: Path) -> str | None:
    from cascade.review import review_record_for_feature

    record = review_record_for_feature(predecessor_id, root=root)
    if record is None:
        return None
    branch = str(record.get("source_branch") or "").strip()
    return branch or None


def _dispatch_record(trunk: Path, feature_id: str) -> dict[str, object] | None:
    record = _load(trunk).get(feature_id)
    return dict(record) if isinstance(record, dict) else None


def _set_dispatch_record(trunk: Path, feature_id: str, record: dict[str, object]) -> None:
    with process_lock:
        features = _load(trunk)
        features[feature_id] = record
        _save(trunk, features)


def _predecessor_review_merged(predecessor_id: str, *, root: Path) -> bool:
    from cascade.review import review_record_for_feature

    record = review_record_for_feature(predecessor_id, root=root)
    if record is None:
        return False
    return bool(record.get("closed"))


def feature_stacked_dispatch_view(feature_id: str, *, root: Path) -> dict[str, object] | None:
    """Operator-facing stacked dispatch and native-retarget reconciliation state."""

    trunk = locate_trunk(root)
    record = _dispatch_record(trunk, feature_id)
    if record is None:
        return None
    base = str(record.get("base_branch") or "").strip()
    if not base:
        return None
    predecessor = record.get("predecessor_id")
    pred_id = str(predecessor).strip() if isinstance(predecessor, str) and predecessor else None
    retarget = record.get("retarget")
    view: dict[str, object] = {
        "base_branch": base,
        "predecessor_id": pred_id,
    }
    if isinstance(retarget, dict):
        state = str(retarget.get("state") or "").strip()
        if state:
            view["retarget_state"] = state
        expected = str(retarget.get("expected_base") or "").strip()
        actual = str(retarget.get("actual_base") or "").strip()
        if expected:
            view["retarget_expected_base"] = expected
        if actual:
            view["retarget_actual_base"] = actual
    return view


def reconcile_stacked_native_retargeting(root: Path) -> dict[str, list[str]]:
    """Verify forge-native base retargeting after a stacked predecessor merges.

    Does not edit pull requests on the provider. Updates durable dispatch state
    and local review registry only when the live PR base matches the epic line.
    """

    trunk = locate_trunk(root)
    board = merged_board(trunk)
    reconciled: list[str] = []
    stale: list[str] = []
    blocked: list[str] = []
    from cascade.review import (
        live_merge_request_target_branch,
        persist_review_target_branch,
        review_record_for_feature,
    )

    for feature_id, record in list(_load(trunk).items()):
        predecessor_id = record.get("predecessor_id")
        if not isinstance(predecessor_id, str) or not predecessor_id.strip():
            continue
        predecessor_id = predecessor_id.strip()
        if not _predecessor_review_merged(predecessor_id, root=trunk):
            continue

        meta = board.by_id.get(feature_id)
        epic_id = meta.parent if meta is not None else None
        if not epic_id:
            blocked.append(feature_id)
            record = dict(record)
            record["retarget"] = {
                "state": "missing_pr_identity",
                "expected_base": "",
                "actual_base": "",
            }
            _set_dispatch_record(trunk, feature_id, record)
            continue

        expected_base = integration_branch("epic", epic_id)
        review_record = review_record_for_feature(feature_id, root=trunk)
        if review_record is None or not str(review_record.get("url") or "").strip():
            blocked.append(feature_id)
            record = dict(record)
            record["retarget"] = {
                "state": "missing_pr_identity",
                "expected_base": expected_base,
                "actual_base": "",
            }
            _set_dispatch_record(trunk, feature_id, record)
            continue

        actual_base = live_merge_request_target_branch(review_record, root=trunk)
        if not actual_base:
            blocked.append(feature_id)
            record = dict(record)
            record["retarget"] = {
                "state": "missing_pr_identity",
                "expected_base": expected_base,
                "actual_base": "",
            }
            _set_dispatch_record(trunk, feature_id, record)
            continue

        if actual_base != expected_base:
            stale.append(feature_id)
            record = dict(record)
            record["retarget"] = {
                "state": "stale_base",
                "expected_base": expected_base,
                "actual_base": actual_base,
            }
            _set_dispatch_record(trunk, feature_id, record)
            continue

        record = dict(record)
        record["predecessor_id"] = None
        record["base_branch"] = expected_base
        record["retarget"] = {"state": "reconciled", "expected_base": expected_base, "actual_base": actual_base}
        _set_dispatch_record(trunk, feature_id, record)

        persist_review_target_branch(feature_id, expected_base, root=trunk)

        reconciled.append(feature_id)

    return {"reconciled": reconciled, "stale": stale, "blocked": blocked}
