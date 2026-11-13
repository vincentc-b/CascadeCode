"""Stacked feature dispatch: base selection, durable state, and completion gates (feat_007_001)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cascade.board.types import BoardIndex, WorkMeta
from cascade.dependency_evaluation import evaluate_dependencies
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


@dataclass(frozen=True)
class FeatureDispatchBlockers:
    """Feature identities currently occupying serial dispatch gates.

    Execution and review are deliberately separate: an active sibling is work
    in progress, while a completed/backlog feature with an open review is
    waiting for merge/review.  ``pending_review_ids`` can also contain a
    declared feature dependency outside this Epic because that review is a
    canonical merge gate, but only same-Epic IDs appear in
    ``pending_sibling_review_ids``.
    """

    active_execution_ids: tuple[str, ...] = ()
    pending_review_ids: tuple[str, ...] = ()
    pending_sibling_review_ids: tuple[str, ...] = ()

    @property
    def blocking_sibling_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(set(self.active_execution_ids) | set(self.pending_sibling_review_ids))
        )


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
    return evaluate_dependencies(meta, root=root, board=board).satisfied


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

    if not meta.parent:
        return True
    return bool(
        feature_dispatch_blockers(
            meta, board, root=root, pending_review_ids=pending_review_ids
        ).pending_review_ids
    )


def feature_dispatch_blockers(
    meta: WorkMeta,
    board: BoardIndex,
    *,
    root: Path,
    pending_review_ids: frozenset[str] | None = None,
) -> FeatureDispatchBlockers:
    """Return all feature IDs blocking serial execution or merge/review.

    A caller-owned review snapshot avoids repeated registry reads during board
    polling.  This projection performs no Git ancestry or provider probes.
    """

    epic_id = meta.parent or ""
    if not epic_id:
        return FeatureDispatchBlockers()

    siblings = tuple(
        feature
        for feature in board.by_id.values()
        if feature.id != meta.id
        and feature.tier == "feature"
        and feature.parent == epic_id
    )
    active_ids = tuple(
        sorted(
            feature.id
            for feature in siblings
            if feature.path.parent.name == "2_active" and feature.status != "completed"
        )
    )

    if effective_stacked_pr_enabled(meta.id, epic_id, root=root):
        return FeatureDispatchBlockers(active_execution_ids=active_ids)

    candidates = {feature.id: feature for feature in siblings}
    candidates.setdefault(meta.id, meta)
    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is not None and dep.tier == "feature" and dep.id != meta.id:
            candidates.setdefault(dep.id, dep)

    if pending_review_ids is None:
        from cascade.review import feature_review_pending

        review_ids = {
            feature_id
            for feature_id in candidates
            if feature_review_pending(feature_id, root=root)
        }
    else:
        review_ids = set(candidates).intersection(pending_review_ids)

    # An executing sibling's primary wait is execution.  Do not describe the
    # same identity a second time as a review wait until execution has ended.
    review_ids.difference_update(active_ids)
    sibling_ids = {feature.id for feature in siblings}
    return FeatureDispatchBlockers(
        active_execution_ids=active_ids,
        pending_review_ids=tuple(sorted(review_ids)),
        pending_sibling_review_ids=tuple(sorted(review_ids.intersection(sibling_ids))),
    )


def feature_dispatch_blocked_by_sibling(
    meta: WorkMeta,
    board: BoardIndex,
    *,
    root: Path,
    pending_review_ids: frozenset[str] | None = None,
) -> bool:
    if not meta.parent:
        return True
    blockers = feature_dispatch_blockers(
        meta, board, root=root, pending_review_ids=pending_review_ids
    )
    return bool(blockers.blocking_sibling_ids)


def plan_feature_dispatch(
    feature_id: str, meta: WorkMeta, board: BoardIndex, *, root: Path
) -> FeatureDispatchPlan:
    epic_id = meta.parent or ""
    if not epic_id:
        return FeatureDispatchPlan(ok=False, reason="bad_state")

    stacked = effective_stacked_pr_enabled(feature_id, epic_id, root=root)
    preds = direct_feature_predecessors(meta, board)
    bases = {
        pred_id: _stacked_predecessor_base(pred_id, board, root=root)
        for pred_id in preds
    } if stacked else {}
    if "missing_predecessor_pr_identity" in bases.values():
        return FeatureDispatchPlan(ok=False, reason="missing_predecessor_pr_identity")
    open_bases = {pred_id: branch for pred_id, branch in bases.items() if branch is not None}
    if stacked and len(preds) > 1 and open_bases:
        # Multiple declarations may describe one existing stack (A -> B,
        # C depends on A and B). Only select a head that actually contains all
        # required work; dependency declarations alone are not Git evidence.
        covering = _covering_predecessor(
            open_bases,
            epic_branch=integration_branch("epic", epic_id),
            require_epic=len(open_bases) < len(bases),
            root=root,
        )
        if covering is None:
            return FeatureDispatchPlan(ok=False, reason="unsupported_topology")
        open_bases = {covering: open_bases[covering]}

    if not feature_dependency_ready(meta, board, root=root):
        return FeatureDispatchPlan(ok=False, reason="unmet_deps")

    epic_branch = integration_branch("epic", epic_id)
    predecessor_id: str | None = None
    base_branch = epic_branch

    if open_bases:
        predecessor_id, base_branch = next(iter(open_bases.items()))

    return FeatureDispatchPlan(
        ok=True,
        selection=FeatureDispatchSelection(
            feature_id=feature_id,
            base_branch=base_branch,
            predecessor_id=predecessor_id,
        ),
    )


def _covering_predecessor(
    branches: dict[str, str], *, epic_branch: str, require_epic: bool, root: Path
) -> str | None:
    """Prove one local review head includes every required predecessor head."""
    repo = locate_trunk(root)

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, timeout=5,
        )

    try:
        heads: dict[str, str] = {}
        required = list(branches.values())
        if require_epic:
            # Closed reviews live on the Epic. Do not pick an open stack that
            # predates accepted work from another declared predecessor.
            required.append(epic_branch)
        for branch in required:
            resolved = git("rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}")
            if resolved.returncode != 0:
                return None
            heads[branch] = resolved.stdout.strip()
        candidates = [
            pred_id for pred_id, branch in branches.items()
            if all(git("merge-base", "--is-ancestor", sha, heads[branch]).returncode == 0
                   for sha in heads.values())
        ]
    except (OSError, subprocess.TimeoutExpired):
        return None
    return candidates[0] if len(candidates) == 1 else None


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
        # Dispatch can precede the upstream merge by hours. If that merge lands
        # before this feature opens its review, GitHub has no open PR to retarget.
        # Refresh only the unpublished choice; an existing PR keeps its own
        # durable target and is handled by native-retarget reconciliation.
        if (
            selection.predecessor_id
            and _predecessor_review_merged(selection.predecessor_id, root=root)
            and not feature_pull_request_linked(feature_id, root=root)
        ):
            base = integration_branch("epic", epic_id)
            persist_feature_dispatch_selection(
                FeatureDispatchSelection(feature_id, base, None), root=root
            )
            return base
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
