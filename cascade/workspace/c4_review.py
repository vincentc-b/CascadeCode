"""Owner-scoped, revision-pinned data for paired C4 review clients."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from cascade.workspace.architecture_review import ArchitectureReviewUnit
from cascade.workspace.c4_bindings import C4BindingError, validate_hit_target_manifest
from cascade.workspace.c4_diff import C4SemanticDiff, C4SemanticModelArtifact
from cascade.workspace.errors import WorkspaceError


ReviewPayloadState = Literal[
    "ready", "unchanged", "first", "empty", "removed", "error"
]


@dataclass(frozen=True)
class C4ReviewTarget:
    kind: Literal["element", "relationship"]
    semantic_id: str


@dataclass(frozen=True)
class C4ReviewSide:
    repository_key: str
    revision: str
    svg: str
    targets: tuple[C4ReviewTarget, ...]


@dataclass(frozen=True)
class C4ReviewView:
    key: str
    level: str
    state: str
    current: C4ReviewSide | None
    proposed: C4ReviewSide | None


@dataclass(frozen=True)
class C4ReviewPayload:
    """Serializable review data; errors remain useful and always name the diff."""

    state: ReviewPayloadState
    owner_work_id: str
    authorized_owner: str
    review_unit_id: str
    reviewed_tuple_digest: str
    repositories: tuple[dict[str, str], ...]
    views: tuple[C4ReviewView, ...]
    changed_views: tuple[tuple[str, str], ...]
    legend: tuple[dict[str, str], ...]
    summary: str
    requirements: tuple[str, ...]
    decisions: tuple[str, ...]
    diffs: dict[str, object]
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _LoadedView:
    key: str
    level: str
    side: C4ReviewSide


_LEGEND = (
    {"state": "added", "meaning": "present only in proposed"},
    {"state": "removed", "meaning": "present only in current"},
    {"state": "changed", "meaning": "semantic content changed"},
    {"state": "unchanged", "meaning": "no semantic change"},
)


def compose_c4_review_payload(
    unit: ArchitectureReviewUnit,
    diff: C4SemanticDiff,
    *,
    owner: str,
    work_id: str,
    current: C4SemanticModelArtifact | None,
    proposed: C4SemanticModelArtifact | None,
    plan_diff_reference: str,
) -> C4ReviewPayload:
    """Compose one exact review unit without heuristic artifact matching.

    View identity is the typed semantic-workspace collection plus its stable key.
    Labels, coordinates, list position, export IDs, and transient SVG IDs are never
    considered.  Artifact validation failures are returned as visible error data.
    """

    if owner != unit.authorized_owner or work_id != unit.owner_work_id:
        raise WorkspaceError("architecture review payload is outside the requested owner scope")
    if not plan_diff_reference.strip():
        raise ValueError("plan_diff_reference must be nonempty")

    base_diffs: dict[str, object] = {
        "source": diff.source_diff_reference,
        "model": _model_diff(diff),
        "plan": plan_diff_reference,
    }
    common = {
        "owner_work_id": unit.owner_work_id,
        "authorized_owner": unit.authorized_owner,
        "review_unit_id": unit.review_unit_id,
        "reviewed_tuple_digest": unit.reviewed_tuple_digest,
        "legend": _LEGEND,
        "summary": diff.summary,
        "requirements": unit.requirement_citations,
        "decisions": unit.decision_citations,
        "diffs": base_diffs,
    }

    try:
        _validate_diff_artifacts(diff, current, proposed)
        if diff.state == "render_error":
            raise C4BindingError(diff.error or diff.summary)
        if (
            proposed is not None
            and proposed.render.status == "ready"
            and proposed.render.source_diff_reference != diff.source_diff_reference
        ):
            raise C4BindingError("proposed render and semantic diff name different source diffs")
        current_views, current_repo = _load_side(unit, current, proposed_side=False)
        proposed_views, proposed_repo = _load_side(unit, proposed, proposed_side=True)
        keyed_current = {(item.key, item.level): item for item in current_views}
        keyed_proposed = {(item.key, item.level): item for item in proposed_views}
        identities = sorted(set(keyed_current) | set(keyed_proposed))
        changed_keys = set(diff.changed_view_keys)
        views = tuple(
            C4ReviewView(
                key=key,
                level=level,
                state=_view_state(key, keyed_current.get((key, level)),
                                  keyed_proposed.get((key, level)), diff),
                current=keyed_current[(key, level)].side
                if (key, level) in keyed_current else None,
                proposed=keyed_proposed[(key, level)].side
                if (key, level) in keyed_proposed else None,
            )
            for key, level in identities
        )
        changed = tuple((view.key, view.level) for view in views if view.key in changed_keys)
        represented = {key for key, _ in changed}
        missing = changed_keys - represented
        if missing:
            raise C4BindingError(
                f"changed view inventory has no exact artifact binding: {sorted(missing)}"
            )
        repositories = tuple(
            row for row in (current_repo, proposed_repo) if row is not None
        )
        return C4ReviewPayload(
            state=_payload_state(diff), repositories=repositories, views=views,
            changed_views=changed, error=None, **common,
        )
    except (C4BindingError, OSError, ValueError, json.JSONDecodeError) as exc:
        # Failure data deliberately retains the source/model/plan diffs.  A
        # consumer must never substitute a static render or guess a pairing.
        return C4ReviewPayload(
            state="error", repositories=(), views=(), changed_views=(),
            error=str(exc), **common,
        )


def _load_side(
    unit: ArchitectureReviewUnit,
    artifact: C4SemanticModelArtifact | None,
    *,
    proposed_side: bool,
) -> tuple[tuple[_LoadedView, ...], dict[str, str] | None]:
    binding = unit.proposed_model if proposed_side else unit.accepted_baseline.model
    if artifact is None:
        if binding is not None:
            raise C4BindingError("pinned model has no corresponding rendered artifact")
        return (), None
    if binding is None:
        if artifact.render.status in {"first", "empty"}:
            return (), None
        raise C4BindingError("rendered artifact has no pinned model binding")
    reference = binding.contract.reference
    render = artifact.render
    if render.status in {"first", "empty"}:
        if render.revision is not None and render.revision != reference.revision:
            raise C4BindingError("empty render does not match its pinned revision")
        return (), {
            "side": "proposed" if proposed_side else "current",
            "repository_key": reference.destination_repository_key,
            "revision": reference.revision,
        }
    if render.status != "ready" or not render.interactive:
        raise C4BindingError(f"rendered artifact is not interactively reviewable: {render.status}")
    if render.revision != reference.revision:
        raise C4BindingError(
            f"render revision {render.revision!r} does not match pinned revision "
            f"{reference.revision!r}"
        )
    if render.binding_manifest is None or render.artifact_directory is None:
        raise C4BindingError("rendered artifact has no hit-target manifest")
    workspace = _read_semantic_workspace(artifact)
    manifest = json.loads(render.binding_manifest.read_text(encoding="utf-8"))
    validate_hit_target_manifest(
        workspace=workspace,
        manifest=manifest,
        artifact_root=render.artifact_directory,
        expected_view_keys=render.view_keys,
        expected_semantic_ids=artifact.contract.semantic_ids,
    )
    levels = _view_levels(workspace, render.view_keys)
    manifest_rows = {row["view_key"]: row for row in manifest["views"]}
    result: list[_LoadedView] = []
    for key in render.view_keys:
        row = manifest_rows[key]
        targets = tuple(sorted(
            (
                C4ReviewTarget(target["kind"], target["semantic_id"])
                for target in row["targets"]
            ),
            key=lambda target: (target.kind, target.semantic_id),
        ))
        result.append(
            _LoadedView(
                key,
                levels[key],
                C4ReviewSide(
                    reference.destination_repository_key,
                    reference.revision,
                    row["svg"],
                    targets,
                ),
            )
        )
    repository = {
        "side": "proposed" if proposed_side else "current",
        "repository_key": reference.destination_repository_key,
        "revision": reference.revision,
    }
    return tuple(result), repository


def _read_semantic_workspace(artifact: C4SemanticModelArtifact) -> dict[str, object]:
    path = artifact.render.semantic_workspace
    digest = artifact.render.semantic_workspace_sha256
    if path is None or digest is None:
        raise C4BindingError("rendered artifact has no pinned semantic workspace")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise C4BindingError("semantic workspace bytes changed after validation")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise C4BindingError("semantic workspace is not an object")
    return value


def _view_levels(
    workspace: dict[str, object], expected: tuple[str, ...]
) -> dict[str, str]:
    raw_views = workspace.get("views")
    if not isinstance(raw_views, dict):
        raise C4BindingError("semantic workspace has no view inventory")
    levels: dict[str, str] = {}
    for level, rows in raw_views.items():
        if not level.endswith("Views"):
            continue
        if not isinstance(rows, list):
            raise C4BindingError(f"semantic view level {level!r} is invalid")
        for row in rows:
            key = row.get("key") if isinstance(row, dict) else None
            if not isinstance(key, str) or not key or key in levels:
                raise C4BindingError("semantic workspace has an ambiguous view binding")
            levels[key] = level
    if set(levels) != set(expected):
        raise C4BindingError("semantic and rendered view inventories disagree")
    return levels


def _validate_diff_artifacts(
    diff: C4SemanticDiff,
    current: C4SemanticModelArtifact | None,
    proposed: C4SemanticModelArtifact | None,
) -> None:
    current_ref = current.artifact_ref if current else None
    proposed_ref = proposed.artifact_ref if proposed else None
    if diff.current_artifact_ref != current_ref or diff.proposed_artifact_ref != proposed_ref:
        raise C4BindingError("semantic diff does not name the supplied artifacts")


def _view_state(
    key: str,
    current: _LoadedView | None,
    proposed: _LoadedView | None,
    diff: C4SemanticDiff,
) -> str:
    if current is None:
        return "added"
    if proposed is None:
        return "removed"
    return next((view.state for view in diff.views if view.key == key), "unchanged")


def _payload_state(diff: C4SemanticDiff) -> ReviewPayloadState:
    return {
        "first_model": "first",
        "empty_baseline": "empty",
        "empty_proposal": "removed",
        "render_error": "error",
        "unchanged": "unchanged",
        "changed": "ready",
    }[diff.state]


def _model_diff(diff: C4SemanticDiff) -> dict[str, object]:
    return {
        "state": diff.state,
        "identities": [asdict(item) for item in diff.identities],
        "containment": [asdict(item) for item in diff.containment],
        "views": [asdict(item) for item in diff.views],
        "changed_view_keys": list(diff.changed_view_keys),
        "error": diff.error,
    }
