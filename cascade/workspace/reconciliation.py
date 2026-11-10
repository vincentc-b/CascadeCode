"""Revision-bound implementation-to-architecture closeout receipts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from cascade.board.errors import NotFound
from cascade.workspace.architecture_review import (
    ArchitectureProposalError,
    ArchitectureReviewStore,
    PinnedArchitectureArtifact,
)
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext

_REVISION = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_SCHEMA_VERSION = 1
ReconciliationOutcome = Literal["accepted_update", "no_change"]
ReconciliationState = Literal["reconciled", "material_mismatch"]


@dataclass(frozen=True)
class ReconciledDesign:
    """One inspected design or ancestor summary before and after reconciliation."""

    before: PinnedArchitectureArtifact
    after: PinnedArchitectureArtifact

    def __post_init__(self) -> None:
        before = self.before.reference
        after = self.after.reference
        if (
            before.target_repository_key,
            before.destination_repository_key,
            before.destination_repository_role,
            before.repository_path,
            before.owning_work,
        ) != (
            after.target_repository_key,
            after.destination_repository_key,
            after.destination_repository_role,
            after.repository_path,
            after.owning_work,
        ):
            raise WorkspaceError("reconciled design identity changed")

    def to_dict(self) -> dict[str, object]:
        return {"before": self.before.to_dict(), "after": self.after.to_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "ReconciledDesign":
        if not isinstance(value, dict) or set(value) != {"before", "after"}:
            raise WorkspaceError("invalid reconciled design")
        return cls(
            PinnedArchitectureArtifact.from_dict(value["before"]),
            PinnedArchitectureArtifact.from_dict(value["after"]),
        )


@dataclass(frozen=True)
class ReconciliationReceipt:
    """Exact implementation, design, lineage, and C4 evidence for one closeout."""

    work_id: str
    tier: Literal["task", "feature", "epic"]
    target_repository_key: str
    integration_lineage: str
    implementation_revisions: tuple[str, ...]
    implementation_head: str
    affected_code_directories: tuple[Path, ...]
    leaf_designs: tuple[ReconciledDesign, ...]
    ancestor_designs: tuple[ReconciledDesign, ...]
    baseline_pointer_id: str | None
    baseline_generation: int | None
    semantic_artifact_digest: str | None
    affected_view_keys: tuple[str, ...]
    outcome: ReconciliationOutcome
    accepted_review_unit_id: str | None = None
    promotion_operation_id: str | None = None
    no_change_reason: str | None = None
    state: ReconciliationState = "reconciled"
    mismatch_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, field in (
            (self.work_id, "work ID"),
            (self.target_repository_key, "target repository key"),
            (self.integration_lineage, "integration lineage"),
        ):
            if not value.strip():
                raise WorkspaceError(f"reconciliation {field} must be non-blank")
        if self.tier not in {"task", "feature", "epic"}:
            raise WorkspaceError("invalid reconciliation tier")
        if not self.implementation_revisions or self.implementation_head not in self.implementation_revisions:
            raise WorkspaceError("reconciliation must include its implementation head")
        for revision in self.implementation_revisions:
            if not _REVISION.fullmatch(revision):
                raise WorkspaceError("invalid reconciled implementation revision")
        if len(set(self.implementation_revisions)) != len(self.implementation_revisions):
            raise WorkspaceError("reconciled implementation revisions must be unique")
        if not self.affected_code_directories or not self.leaf_designs:
            raise WorkspaceError("reconciliation requires affected code and leaf designs")
        _unique_paths(self.affected_code_directories, "affected code directories")
        designs = (*self.leaf_designs, *self.ancestor_designs)
        paths = [item.after.reference.repository_path for item in designs]
        if len(paths) != len(set(paths)):
            raise WorkspaceError("reconciled design paths must be unique")
        if (self.baseline_pointer_id is None) != (self.baseline_generation is None):
            raise WorkspaceError("baseline pointer and generation must be recorded together")
        if self.baseline_generation is not None and (
            isinstance(self.baseline_generation, bool) or self.baseline_generation < 1
        ):
            raise WorkspaceError("invalid reconciliation baseline generation")
        if self.semantic_artifact_digest is not None and not _DIGEST.fullmatch(
            self.semantic_artifact_digest
        ):
            raise WorkspaceError("invalid reconciliation semantic artifact digest")
        _unique_strings(self.affected_view_keys, "affected view keys")
        _unique_strings(self.mismatch_reasons, "mismatch reasons")
        if self.outcome == "accepted_update":
            if not self.accepted_review_unit_id or self.no_change_reason is not None:
                raise WorkspaceError("accepted update requires only its review evidence")
        elif self.outcome == "no_change":
            if (
                not self.no_change_reason
                or not self.no_change_reason.strip()
                or self.accepted_review_unit_id is not None
                or self.promotion_operation_id is not None
            ):
                raise WorkspaceError("no-change reconciliation requires only a justification")
            if any(item.before != item.after for item in designs):
                raise WorkspaceError("no-change reconciliation cannot contain design updates")
        else:
            raise WorkspaceError("invalid reconciliation outcome")
        if self.state == "material_mismatch":
            if not self.mismatch_reasons:
                raise WorkspaceError("material mismatch requires reasons")
        elif self.state != "reconciled" or self.mismatch_reasons:
            raise WorkspaceError("invalid reconciliation state")

    def to_dict(self) -> dict[str, object]:
        return {
            "work_id": self.work_id,
            "tier": self.tier,
            "target_repository_key": self.target_repository_key,
            "integration_lineage": self.integration_lineage,
            "implementation_revisions": list(self.implementation_revisions),
            "implementation_head": self.implementation_head,
            "affected_code_directories": [path.as_posix() for path in self.affected_code_directories],
            "leaf_designs": [item.to_dict() for item in self.leaf_designs],
            "ancestor_designs": [item.to_dict() for item in self.ancestor_designs],
            "baseline_pointer_id": self.baseline_pointer_id,
            "baseline_generation": self.baseline_generation,
            "semantic_artifact_digest": self.semantic_artifact_digest,
            "affected_view_keys": list(self.affected_view_keys),
            "outcome": self.outcome,
            "accepted_review_unit_id": self.accepted_review_unit_id,
            "promotion_operation_id": self.promotion_operation_id,
            "no_change_reason": self.no_change_reason,
            "state": self.state,
            "mismatch_reasons": list(self.mismatch_reasons),
        }

    @classmethod
    def from_dict(cls, value: object) -> "ReconciliationReceipt":
        fields = {
            "work_id", "tier", "target_repository_key", "integration_lineage",
            "implementation_revisions", "implementation_head", "affected_code_directories",
            "leaf_designs", "ancestor_designs", "baseline_pointer_id", "baseline_generation",
            "semantic_artifact_digest", "affected_view_keys", "outcome",
            "accepted_review_unit_id", "promotion_operation_id", "no_change_reason", "state",
            "mismatch_reasons",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise WorkspaceError("invalid reconciliation receipt")
        try:
            return cls(
                work_id=value["work_id"], tier=value["tier"],
                target_repository_key=value["target_repository_key"],
                integration_lineage=value["integration_lineage"],
                implementation_revisions=tuple(value["implementation_revisions"]),
                implementation_head=value["implementation_head"],
                affected_code_directories=tuple(Path(item) for item in value["affected_code_directories"]),
                leaf_designs=tuple(ReconciledDesign.from_dict(item) for item in value["leaf_designs"]),
                ancestor_designs=tuple(ReconciledDesign.from_dict(item) for item in value["ancestor_designs"]),
                baseline_pointer_id=value["baseline_pointer_id"],
                baseline_generation=value["baseline_generation"],
                semantic_artifact_digest=value["semantic_artifact_digest"],
                affected_view_keys=tuple(value["affected_view_keys"]), outcome=value["outcome"],
                accepted_review_unit_id=value["accepted_review_unit_id"],
                promotion_operation_id=value["promotion_operation_id"],
                no_change_reason=value["no_change_reason"], state=value["state"],
                mismatch_reasons=tuple(value["mismatch_reasons"]),
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError("invalid reconciliation receipt") from exc


class ReconciliationReceiptStore:
    """Append-only receipt evidence; newer revisions never erase stale receipts."""

    def __init__(self, project: ProjectContext, path: Path | None = None) -> None:
        self.project = project
        self.path = path or project.target.root / "architecture" / "reconciliation-receipts.json"

    def save(self, receipt: ReconciliationReceipt) -> None:
        state = self._read()
        rows = state["receipts"].setdefault(receipt.work_id, [])
        encoded = receipt.to_dict()
        if encoded not in rows:
            rows.append(encoded)
            self._write(state)

    def for_work(self, work_id: str) -> tuple[ReconciliationReceipt, ...]:
        return tuple(
            ReconciliationReceipt.from_dict(item)
            for item in self._read()["receipts"].get(work_id, [])
        )

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"version": _SCHEMA_VERSION, "receipts": {}}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"invalid reconciliation receipt store: {self.path}") from exc
        if (
            not isinstance(state, dict) or set(state) != {"version", "receipts"}
            or state["version"] != _SCHEMA_VERSION or not isinstance(state["receipts"], dict)
        ):
            raise WorkspaceError(f"unsupported reconciliation receipt store: {self.path}")
        return state

    def _write(self, state: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def record_reconciliation_receipt(
    project: ProjectContext,
    receipt: ReconciliationReceipt,
    *,
    review_store: ArchitectureReviewStore | None = None,
    receipt_store: ReconciliationReceiptStore | None = None,
) -> ReconciliationReceipt:
    """Validate and durably append exact closeout evidence under the lifecycle lock."""

    from cascade.task.lifecycle_lock import task_lifecycle_lock

    with task_lifecycle_lock(root=project.target.root):
        reviews = review_store or ArchitectureReviewStore(project)
        _validate_receipt(project, receipt, reviews, require_current_head=False)
        (receipt_store or ReconciliationReceiptStore(project)).save(receipt)
    return receipt


def validate_reconciliation_closeout(
    project: ProjectContext,
    work_id: str,
    tier: Literal["task", "feature", "epic"],
    *,
    implementation_revision: str | None = None,
    review_store: ArchitectureReviewStore | None = None,
    receipt_store: ReconciliationReceiptStore | None = None,
) -> ReconciliationReceipt:
    """Require the current reconciled receipt before a terminal state change."""

    reviews = review_store or ArchitectureReviewStore(project)
    if hold := reviews.acceptance_hold(work_id):
        raise ArchitectureProposalError(
            "acceptance_pending", f"split-repository promotion {hold} has not landed on both sides"
        )
    head = implementation_revision or resolve_closeout_revision(project, work_id, tier)
    receipts = (receipt_store or ReconciliationReceiptStore(project)).for_work(work_id)
    current = next((item for item in reversed(receipts) if item.implementation_head == head), None)
    if current is None:
        code = "missing_reconciliation" if not receipts else "stale_reconciliation"
        raise ArchitectureProposalError(code, f"no reconciliation receipt covers implementation {head}")
    if current.tier != tier:
        raise ArchitectureProposalError("stale_reconciliation", "receipt tier differs from closeout tier")
    _validate_receipt(project, current, reviews, require_current_head=True)
    if current.state == "material_mismatch":
        raise ArchitectureProposalError(
            "material_mismatch", "; ".join(current.mismatch_reasons)
        )
    return current


def resolve_closeout_revision(
    project: ProjectContext, work_id: str, tier: Literal["task", "feature", "epic"]
) -> str:
    prefix = {"task": "task", "feature": "feat", "epic": "epic"}[tier]
    branch = f"refs/heads/{prefix}/{work_id}"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch], cwd=project.target.root,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project.target.root,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        )
    revision = result.stdout.strip()
    if result.returncode != 0 or not _REVISION.fullmatch(revision):
        raise ArchitectureProposalError("stale_reconciliation", "cannot resolve closeout revision")
    return revision


def _validate_receipt(
    project: ProjectContext,
    receipt: ReconciliationReceipt,
    reviews: ArchitectureReviewStore,
    *,
    require_current_head: bool,
) -> None:
    if receipt.target_repository_key != project.target_repository_key:
        raise ArchitectureProposalError("stale_reconciliation", "receipt belongs to another target")
    _require_work_tier(project, receipt.work_id, receipt.tier)
    for revision in receipt.implementation_revisions:
        _require_commit(project.target.root, revision)
        if not _is_ancestor(project.target.root, revision, receipt.implementation_head):
            raise ArchitectureProposalError(
                "stale_reconciliation", "inspected implementation revisions do not form one head"
            )
    units = reviews.units_affecting(receipt.work_id)
    relevant = tuple(unit for unit in units if unit.integration_lineage == receipt.integration_lineage)
    expected_leaf = {
        unit.design.reference.repository_path
        for unit in relevant if unit.owner_work_id == receipt.work_id
    }
    expected_ancestors = {
        unit.design.reference.repository_path
        for unit in relevant if unit.owner_work_id != receipt.work_id
    }
    recorded_leaf = {item.after.reference.repository_path for item in receipt.leaf_designs}
    recorded_ancestors = {item.after.reference.repository_path for item in receipt.ancestor_designs}
    missing = (expected_leaf - recorded_leaf) | (expected_ancestors - recorded_ancestors)
    if missing:
        raise ArchitectureProposalError(
            "affected_design_missing",
            "receipt omits affected designs: " + ", ".join(sorted(path.as_posix() for path in missing)),
        )
    misclassified = (expected_leaf & recorded_ancestors) | (expected_ancestors & recorded_leaf)
    if misclassified:
        raise ArchitectureProposalError(
            "affected_design_missing",
            "receipt misclassifies leaf and ancestor designs: "
            + ", ".join(sorted(path.as_posix() for path in misclassified)),
        )
    leaf_directories = {
        item.after.reference.code_directory for item in receipt.leaf_designs
    }
    if any(
        not any(_path_contains(owner, affected) for owner in leaf_directories)
        for affected in receipt.affected_code_directories
    ):
        raise ArchitectureProposalError(
            "affected_design_missing", "affected code directory has no mapped leaf design"
        )
    for design in (*receipt.leaf_designs, *receipt.ancestor_designs):
        _verify_artifact(project, design.before)
        _verify_artifact(project, design.after)
    current = reviews.resolve_current(
        receipt.integration_lineage, lineage_revision=receipt.implementation_head
    )
    pointer = current.pointer_id if current is not None else None
    generation = current.generation if current is not None else None
    if (receipt.baseline_pointer_id, receipt.baseline_generation) != (pointer, generation):
        raise ArchitectureProposalError("stale_reconciliation", "accepted baseline changed")
    expected_semantic = (
        current.baseline.model.semantic_artifact_digest
        if current is not None and current.baseline.model is not None else None
    )
    if receipt.semantic_artifact_digest != expected_semantic:
        raise ArchitectureProposalError("stale_reconciliation", "inspected C4 semantic artifact changed")
    expected_views = {view for unit in relevant for view in unit.view_citations}
    if not expected_views.issubset(receipt.affected_view_keys):
        raise ArchitectureProposalError("affected_design_missing", "receipt omits affected C4 views")
    if receipt.outcome == "accepted_update":
        unit = reviews.get(receipt.accepted_review_unit_id or "")
        if unit is None or unit not in relevant:
            raise ArchitectureProposalError("review_required", "receipt update is not in affected scope")
        if current is None or current.accepted_review_unit_id != unit.review_unit_id:
            raise ArchitectureProposalError("stale_reconciliation", "receipt update is not accepted")
        if current.accepted_design not in tuple(
            item.after for item in (*receipt.leaf_designs, *receipt.ancestor_designs)
        ):
            raise ArchitectureProposalError(
                "stale_reconciliation", "receipt omits the accepted design revision"
            )
        if receipt.promotion_operation_id is not None:
            promotion = reviews.get_promotion(receipt.promotion_operation_id)
            if promotion is None or promotion.outcome != "accepted":
                raise ArchitectureProposalError(
                    "acceptance_pending", "promotion reference has not landed on both sides"
                )
    if hold := reviews.acceptance_hold(receipt.work_id):
        raise ArchitectureProposalError(
            "acceptance_pending", f"split-repository promotion {hold} has not landed on both sides"
        )
    if require_current_head and receipt.state == "reconciled":
        # Accepted review units describe the baseline they advanced from, so a
        # generic refresh would incorrectly stale them after their own lineage
        # pointer is installed. Exact artifact bytes and the resulting pointer
        # are checked above; only an already-invalid durable status is refused.
        if any(unit.status in {"stale", "rejected"} for unit in relevant):
            raise ArchitectureProposalError("stale_reconciliation", "reviewed architecture input changed")


def _require_work_tier(project: ProjectContext, work_id: str, tier: str) -> None:
    from cascade.workspace.doc_root import read_doc_resolved

    try:
        doc = read_doc_resolved(work_id, root=project.tracking.root)
    except NotFound:
        raise ArchitectureProposalError("missing_reconciliation", f"unknown work record {work_id}") from None
    if doc.meta.tier != tier:
        raise ArchitectureProposalError("stale_reconciliation", "work tier changed")


def _verify_artifact(project: ProjectContext, artifact: PinnedArchitectureArtifact) -> None:
    reference = artifact.reference
    repository = project.target if reference.destination_repository_role == "target" else project.tracking
    expected_key = project.target_repository_key if reference.destination_repository_role == "target" else repository.repository_key
    if reference.target_repository_key != project.target_repository_key or reference.destination_repository_key != expected_key:
        raise ArchitectureProposalError("stale_reconciliation", "design repository identity changed")
    result = subprocess.run(
        ["git", "show", f"{reference.revision}:{reference.repository_path.as_posix()}"],
        cwd=repository.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    digest = hashlib.sha256(result.stdout).hexdigest()
    if result.returncode != 0 or digest != artifact.content_digest.removeprefix("sha256:"):
        raise ArchitectureProposalError("stale_reconciliation", "inspected design revision changed")


def _require_commit(root: Path, revision: str) -> None:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if result.returncode != 0:
        raise ArchitectureProposalError("stale_reconciliation", f"unknown implementation revision {revision}")


def _is_ancestor(root: Path, revision: str, head: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, head], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0


def _path_contains(owner: Path, affected: Path) -> bool:
    owner_parts = tuple(part for part in owner.parts if part not in {"", "."})
    affected_parts = tuple(part for part in affected.parts if part not in {"", "."})
    return affected_parts[: len(owner_parts)] == owner_parts


def _unique_strings(values: Sequence[str], field: str) -> None:
    if any(not value.strip() for value in values) or len(values) != len(set(values)):
        raise WorkspaceError(f"{field} must be unique and non-blank")


def _unique_paths(values: Sequence[Path], field: str) -> None:
    normalized = []
    for value in values:
        if value.is_absolute() or ".." in value.parts:
            raise WorkspaceError(f"{field} must be repository-relative")
        normalized.append(value.as_posix())
    if len(normalized) != len(set(normalized)):
        raise WorkspaceError(f"{field} must be unique")


__all__ = [
    "ReconciledDesign", "ReconciliationReceipt", "ReconciliationReceiptStore",
    "record_reconciliation_receipt", "resolve_closeout_revision",
    "validate_reconciliation_closeout",
]
