"""Durable publication of authenticated planning architecture reviews."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import get_project_context
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.workspace.architecture_authoring import (
    ArchitectureAuthoringIntent,
    stage_owned_architecture_change,
)
from cascade.workspace.architecture_review import (
    ArchitectureModelBinding,
    ArchitectureProposalError,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    resolve_registered_owner_revision,
    stage_architecture_proposal,
)
from cascade.workspace.c4_closure import materialize_c4_source_closure
from cascade.workspace.c4_diff import C4SemanticModelArtifact
from cascade.workspace.c4_render import C4ArtifactRenderer, C4RenderSettings
from cascade.workspace.c4_scheduler import C4RenderScheduler, render_identity
from cascade.workspace.c4_scheduler import C4RenderAdmissionError
from cascade.workspace.doc_root import read_doc_resolved
from cascade.workspace.integration_worktree import git_root_for_path
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext

PublicationStatus = Literal[
    "pending", "ready", "no_diagram_change", "routed", "failed", "superseded"
]
_LEDGER_VERSION = 1
_LEDGER = Path(".cascade") / "architecture-publications.json"
_schedulers: dict[Path, C4RenderScheduler] = {}
_schedulers_lock = threading.Lock()


def publish_architecture_review(
    *,
    proposal: dict[str, object],
    expected_plan_revision: str,
    expected_generation: int | None,
    actor: str,
    work_id: str,
    root: Path,
) -> dict[str, object]:
    """Persist an exact intent and start bounded rendering when required.

    ``actor`` and ``work_id`` are supplied only by the authenticated planning
    dispatcher.  Repository roles come from launcher-owned ProjectContext.
    """

    project = get_project_context() or ProjectContext.colocated(Path(root))
    unit = _authenticated_unit(
        project, proposal, actor=actor, work_id=work_id,
        expected_plan_revision=expected_plan_revision, root=Path(root),
    )
    store = ArchitectureReviewStore(project)
    if store.pending_promotion(unit.integration_lineage) is not None:
        raise ArchitectureProposalError(
            "acceptance_pending",
            "architecture publication is blocked until both promotion sides land",
        )

    operation_id = _publication_id(work_id, actor, unit, expected_generation)
    pending = False
    with task_lifecycle_lock(root=project.target.root):
        ledger = _read_ledger(project)
        existing = ledger["operations"].get(operation_id)
        if existing is None:
            now = time.time()
            ledger["operations"][operation_id] = {
                "operation_id": operation_id,
                "status": "pending",
                "originating_work_id": work_id,
                "actor": actor,
                "expected_plan_revision": expected_plan_revision,
                "expected_generation": expected_generation,
                "proposal": unit.to_dict(),
                "render_operation_id": None,
                "baseline_render_operation_id": None,
                "review_unit_id": None,
                "reviewed_tuple_digest": unit.reviewed_tuple_digest,
                "amendment_id": None,
                "reason_code": None,
                "message": "architecture publication is pending validation",
                "failure_history": [],
                "created_at": now,
                "updated_at": now,
            }
            _write_ledger(project, ledger)
            pending = True
        else:
            pending = existing.get("status") == "pending"
            if (
                existing.get("status") == "superseded"
                and existing.get("reason_code") == "artifact_changed"
            ):
                history = list(existing.get("failure_history", []))
                history.append({
                    "status": existing["status"],
                    "reason_code": existing.get("reason_code"),
                    "message": existing.get("message"),
                    "updated_at": existing.get("updated_at"),
                })
                existing.update({
                    "status": "pending",
                    "render_operation_id": None,
                    "baseline_render_operation_id": None,
                    "review_unit_id": None,
                    "amendment_id": None,
                    "reason_code": None,
                    "message": "architecture publication retry is pending validation",
                    "failure_history": history,
                    "updated_at": time.time(),
                })
                _write_ledger(project, ledger)
                pending = True
    if pending:
        store.set_acceptance_hold(unit.affected_work_ids, operation_id)

    # Replays and restart discovery always reconcile from durable intent.
    return discover_architecture_publication(operation_id, root=root)


def discover_architecture_publication(
    operation_id: str, *, root: Path
) -> dict[str, object]:
    """Reconcile one durable publication without unbounded caller-thread work."""

    project = get_project_context() or ProjectContext.colocated(Path(root))
    with task_lifecycle_lock(root=project.target.root):
        row = _read_ledger(project)["operations"].get(operation_id)
    if row is None:
        raise KeyError(operation_id)
    if row["status"] not in {"pending"}:
        return _public_result(row)

    unit = ArchitectureReviewUnit.from_dict(row["proposal"])
    store = ArchitectureReviewStore(project)
    try:
        _require_current_plan(
            project,
            unit,
            work_id=str(row["originating_work_id"]),
            expected_revision=str(row["expected_plan_revision"]),
            root=Path(root),
        )
        lineage_revision = resolve_registered_owner_revision(
            project.target, unit.owner_work_id
        )
        if store.pending_promotion(unit.integration_lineage) is not None:
            return _update(
                project, row, "pending", reason_code="acceptance_pending",
                message="waiting for partial architecture acceptance to finish",
            )
        current = store.resolve_current(
            unit.integration_lineage, lineage_revision=lineage_revision
        )
        generation = current.generation if current else None
        if (
            generation != row["expected_generation"]
            or store.baseline_status(
                unit, lineage_revision=lineage_revision
            ).stale
        ):
            return _terminal(
                project, store, row, "superseded", "stale_baseline",
                "accepted architecture baseline changed before publication",
            )

        if unit.architecture_impact == "no_diagram_change":
            return _publish_validated(
                project, store, row, unit, no_diagram=True,
                baseline_artifact=None, lineage_revision=lineage_revision,
            )

        scheduler = _project_scheduler(project)
        proposed_id = row.get("render_operation_id")
        if proposed_id is None:
            proposed_id = _admit_binding(
                project, scheduler, unit.proposed_model, owner=unit.owner_work_id,
                snapshot_id=operation_id,
            )
            _update(
                project, row, "pending", render_operation_id=proposed_id,
                message="bounded architecture render is pending",
            )
            with task_lifecycle_lock(root=project.target.root):
                row = _read_ledger(project)["operations"][operation_id]

        baseline_id = row.get("baseline_render_operation_id")
        baseline_binding = unit.accepted_baseline.model
        if baseline_binding is not None and baseline_id is None:
            baseline_id = _admit_binding(
                project, scheduler, baseline_binding, owner=unit.owner_work_id,
                snapshot_id=f"{operation_id}:baseline",
            )
            _update(
                project, row, "pending", baseline_render_operation_id=baseline_id,
            )
            with task_lifecycle_lock(root=project.target.root):
                row = _read_ledger(project)["operations"][operation_id]

        proposed = scheduler.get(str(proposed_id))
        baseline = scheduler.get(str(baseline_id)) if baseline_id is not None else None
        states = {proposed.status}
        if baseline is not None:
            states.add(baseline.status)
        if states & {"failed", "cancelled"}:
            failure = proposed.failure or (baseline.failure if baseline else None)
            return _terminal(
                project, store, row, "failed",
                failure.code if failure else "render_failed",
                failure.message if failure else "architecture render failed",
            )
        if states & {"pending", "running"}:
            return _public_result(row)
        if proposed.status != "ready" or proposed.artifact is None:
            return _terminal(
                project, store, row, "failed", "render_failed",
                "a claimed diagram change did not produce a semantic artifact",
            )

        # Recheck revision and lineage immediately before current-unit publication.
        _require_current_plan(
            project, unit, work_id=str(row["originating_work_id"]),
            expected_revision=str(row["expected_plan_revision"]), root=Path(root),
        )
        lineage_revision = resolve_registered_owner_revision(
            project.target, unit.owner_work_id
        )
        current = store.resolve_current(
            unit.integration_lineage, lineage_revision=lineage_revision
        )
        generation = current.generation if current else None
        if (
            generation != row["expected_generation"]
            or store.baseline_status(
                unit, lineage_revision=lineage_revision
            ).stale
        ):
            return _terminal(
                project, store, row, "superseded", "stale_baseline",
                "accepted architecture baseline changed during rendering",
            )
        baseline_artifact = None
        if baseline_binding is not None:
            assert baseline is not None and baseline.artifact is not None
            baseline_artifact = _semantic_artifact(
                project, baseline_binding,
                unit.accepted_baseline.accepted_review_unit_id or "accepted-baseline",
                baseline.artifact,
            )
        return _publish_validated(
            project, store, row, unit, no_diagram=False,
            baseline_artifact=baseline_artifact,
            lineage_revision=lineage_revision,
        )
    except ArchitectureProposalError as exc:
        return _terminal(project, store, row, "superseded" if exc.code in {
            "stale_baseline", "artifact_changed", "destination_changed"
        } else "failed", exc.code, str(exc).partition(": ")[2] or str(exc))
    except C4RenderAdmissionError as exc:
        return _update(
            project, row, "pending", reason_code=exc.code, message=str(exc)
        )
    except (OSError, ValueError, WorkspaceError) as exc:
        return _terminal(project, store, row, "failed", "invalid_publication", str(exc))


def _authenticated_unit(
    project: ProjectContext,
    payload: dict[str, object],
    *, actor: str, work_id: str, expected_plan_revision: str, root: Path,
) -> ArchitectureReviewUnit:
    if not isinstance(payload, dict):
        raise ValueError("proposal must be an object")
    normalized = json.loads(json.dumps(payload))
    try:
        owner = normalized["design"]["reference"]["owning_work"]
    except (KeyError, TypeError) as exc:
        raise ValueError("proposal design must identify its committed owner") from exc
    if not isinstance(owner, str) or not owner:
        raise ValueError("proposal design owner must be non-blank")
    owner_doc = read_doc_resolved(owner, root=project.tracking.root)
    owner_actor = {"epic": "epic_architect", "feature": "feature_architect"}.get(
        owner_doc.meta.tier
    )
    if owner_actor is None:
        raise ArchitectureProposalError(
            "owner_denied", "normal planning publication requires an epic or feature owner"
        )
    normalized["owner_work_id"] = owner
    normalized["authorized_owner"] = owner_actor
    normalized["status"] = "draft"
    unit = ArchitectureReviewUnit.from_dict(normalized)
    _require_current_plan(
        project, unit, work_id=work_id, expected_revision=expected_plan_revision,
        root=root,
    )
    if work_id == owner and actor != owner_actor:
        raise ArchitectureProposalError(
            "owner_denied", "only the authenticated architecture owner may publish"
        )
    if unit.proposed_model is not None:
        identity = render_identity(
            unit.proposed_model.source_closure_digest,
            C4RenderSettings(**dict(unit.proposed_model.renderer_settings)),
        )
        unit = replace(
            unit,
            proposed_model=replace(unit.proposed_model, render_identity=identity),
        )
    return unit


def _require_current_plan(
    project: ProjectContext,
    unit: ArchitectureReviewUnit,
    *, work_id: str, expected_revision: str, root: Path,
) -> None:
    if unit.plan.revision != expected_revision:
        raise ArchitectureProposalError(
            "stale_revision", "proposal plan revision differs from the expected revision"
        )
    doc = read_doc_resolved(work_id, root=project.tracking.root)
    plan_repository = (
        project.tracking if unit.plan.repository_role == "tracking" else project.target
    )
    if unit.plan.repository_key != plan_repository.repository_key:
        raise ArchitectureProposalError(
            "stale_revision", "plan reference names a different repository"
        )
    try:
        actual_path = doc.meta.path.resolve().relative_to(
            git_root_for_path(doc.meta.path).resolve()
        )
    except ValueError as exc:
        raise ArchitectureProposalError(
            "stale_revision", "current plan path is outside its Git worktree"
        ) from exc
    if actual_path != unit.plan.path:
        raise ArchitectureProposalError(
            "stale_revision", "proposal does not reference the owning plan document"
        )
    current = doc.sha
    if current is None:
        try:
            repository = plan_repository
            relative = actual_path
        except ValueError as exc:
            raise ArchitectureProposalError("stale_revision", "plan path is outside its repository") from exc
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", relative.as_posix()],
            cwd=repository.root, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False,
        )
        current = result.stdout.strip() if result.returncode == 0 else None
    if current != expected_revision:
        raise ArchitectureProposalError(
            "stale_revision", "plan revision changed before architecture publication"
        )


def _admit_binding(
    project: ProjectContext,
    scheduler: C4RenderScheduler,
    binding: ArchitectureModelBinding | None,
    *, owner: str, snapshot_id: str,
) -> str:
    if binding is None:
        raise ArchitectureProposalError("model_required", "diagram publication has no model")
    with tempfile.TemporaryDirectory(prefix="cascade-publication-") as directory:
        closure = materialize_c4_source_closure(
            project, binding.contract.reference,
            tuple(item.reference for item in binding.sources),
            Path(directory) / "source",
        )
        if closure.digest != binding.source_closure_digest:
            raise ArchitectureProposalError(
                "model_invalid", "committed source inventory differs from its pinned digest"
            )
        settings = C4RenderSettings(**dict(binding.renderer_settings))
        return scheduler.admit(
            closure, settings, owner=owner, snapshot_id=snapshot_id
        ).operation_id


def _semantic_artifact(project, binding, unit_id, artifact):
    with tempfile.TemporaryDirectory(prefix="cascade-baseline-") as directory:
        closure = materialize_c4_source_closure(
            project, binding.contract.reference,
            tuple(item.reference for item in binding.sources),
            Path(directory) / "source",
        )
        return C4SemanticModelArtifact(unit_id, artifact, closure.contract)


def _publish_validated(
    project, store, row, unit, *, no_diagram: bool, baseline_artifact,
    lineage_revision: str,
):
    origin = str(row["originating_work_id"])
    actor = str(row["actor"])
    generation = row["expected_generation"]
    render_settings = (
        C4RenderSettings(**dict(unit.proposed_model.renderer_settings))
        if unit.proposed_model is not None else None
    )
    if origin != unit.owner_work_id:
        result = stage_owned_architecture_change(
            project,
            ArchitectureAuthoringIntent(origin, actor, unit, generation),
            store=store,
            renderer=C4ArtifactRenderer(
                project.target.root / ".cascade" / "c4-render-cache"
            ),
            render_settings=render_settings,
            baseline_artifact=baseline_artifact,
            lineage_revision=lineage_revision,
            plan_work_id=origin,
        )
        assert result.amendment is not None
        return _terminal(
            project, store, row, "routed", "owner_routed",
            "architecture change was routed to its ancestor owner",
            amendment_id=result.amendment.amendment_id,
        )
    staged = stage_architecture_proposal(
        project,
        owner=unit.authorized_owner,
        work_id=unit.owner_work_id,
        proposal=unit,
        expected_generation=generation,
        store=store,
        renderer=C4ArtifactRenderer(
            project.target.root / ".cascade" / "c4-render-cache"
        ),
        render_settings=render_settings,
        baseline_artifact=baseline_artifact,
        lineage_revision=lineage_revision,
        plan_work_id=origin,
    )
    assert staged.unit is not None
    return _terminal(
        project, store, row,
        "no_diagram_change" if no_diagram else "ready", None,
        "explicit no-diagram-change declaration published" if no_diagram
        else "validated architecture review published",
        review_unit_id=staged.unit.review_unit_id,
        reviewed_tuple_digest=staged.unit.reviewed_tuple_digest,
    )


def _terminal(project, store, row, status, code, message, **updates):
    result = _update(
        project, row, status, reason_code=code, message=message, **updates
    )
    for work_id in ArchitectureReviewUnit.from_dict(
        row["proposal"]
    ).affected_work_ids:
        if store.acceptance_hold(work_id) == row["operation_id"]:
            store.set_acceptance_hold((work_id,), None)
    return result


def _update(project, row, status, **updates):
    with task_lifecycle_lock(root=project.target.root):
        ledger = _read_ledger(project)
        durable = ledger["operations"][row["operation_id"]]
        durable.update(updates, status=status, updated_at=time.time())
        _write_ledger(project, ledger)
        return _public_result(durable)


def _public_result(row):
    return {
        key: row.get(key) for key in (
            "operation_id", "status", "render_operation_id",
            "baseline_render_operation_id", "review_unit_id",
            "reviewed_tuple_digest", "amendment_id", "reason_code", "message",
        )
    }


def _publication_id(work_id, actor, unit, generation):
    payload = json.dumps({
        "work_id": work_id, "actor": actor,
        "tuple": unit.reviewed_tuple_digest, "generation": generation,
    }, sort_keys=True, separators=(",", ":")).encode()
    return "architecture-publication-" + hashlib.sha256(payload).hexdigest()


def _project_scheduler(project: ProjectContext) -> C4RenderScheduler:
    root = project.target.root.resolve()
    with _schedulers_lock:
        scheduler = _schedulers.get(root)
        if scheduler is None:
            scheduler = C4RenderScheduler(root)
            _schedulers[root] = scheduler
        return scheduler


def _read_ledger(project: ProjectContext) -> dict[str, Any]:
    path = project.target.root / _LEDGER
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": _LEDGER_VERSION, "operations": {}}
    if not isinstance(value, dict) or value.get("version") != _LEDGER_VERSION or not isinstance(value.get("operations"), dict):
        raise ValueError("architecture publication ledger is invalid")
    return value


def _write_ledger(project: ProjectContext, ledger: dict[str, Any]) -> None:
    path = project.target.root / _LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
