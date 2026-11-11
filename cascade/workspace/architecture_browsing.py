"""Known-checkout and exact documentation refs for architecture browsing.

This module is deliberately a resolver, not a filesystem browser.  A caller
selects an opaque context/ref ID from a server-produced catalog; paths and Git
expressions never cross the boundary.  The returned revisions are full commits
and are suitable inputs for the immutable snapshot service built on top of this
seam.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.workspace.architecture_review import (
    AcceptedLineage,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    PromotionJournal,
)
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.integration_worktree import load_registry_readonly, locate_trunk
from cascade.workspace.reconciliation import ReconciliationReceipt
from cascade.workspace.types import ProjectContext, RepositoryContext

ContextKind = Literal["session_target", "project_worktree"]
AssociationProvenance = Literal[
    "colocated", "review", "promotion", "accepted_lineage", "user_selected"
]


class ArchitectureBrowsingError(WorkspaceError):
    """A selected context or documentation ref is not in the known catalog."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ArchitectureCodeContext:
    context_id: str
    kind: ContextKind
    label: str
    repository_key: str
    revision: str
    branch: str | None
    detached: bool
    dirty: bool
    work_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "context_id": self.context_id,
            "kind": self.kind,
            "label": self.label,
            "repository_key": self.repository_key,
            "revision": self.revision,
            "branch": self.branch,
            "detached": self.detached,
            "dirty": self.dirty,
            "work_id": self.work_id,
        }


@dataclass(frozen=True)
class KnownDocumentationRef:
    ref_id: str
    repository_key: str
    revision: str
    provenance: AssociationProvenance
    evidence_id: str | None = None
    lineage: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ref_id": self.ref_id,
            "repository_key": self.repository_key,
            "revision": self.revision,
            "provenance": self.provenance,
            "evidence_id": self.evidence_id,
            "lineage": self.lineage,
        }


@dataclass(frozen=True)
class ArchitectureContextSelection:
    context: ArchitectureCodeContext
    architecture_destination: Literal["target", "tracking"]
    mapping_repository_key: str
    mapping_revision: str
    documentation_repository_key: str
    documentation_revision: str | None
    association_provenance: AssociationProvenance | None
    association_evidence_id: str | None
    documentation_ref_required: bool
    known_documentation_refs: tuple[KnownDocumentationRef, ...]
    accepted_lineage: KnownDocumentationRef | None = None

    @property
    def state(self) -> str:
        return "documentation_ref_required" if self.documentation_ref_required else "ready"

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "context": self.context.to_dict(),
            "architecture_destination": self.architecture_destination,
            "mapping": {
                "repository_key": self.mapping_repository_key,
                "revision": self.mapping_revision,
                "path": "architecture/design-mappings.json",
            },
            "documentation_repository_key": self.documentation_repository_key,
            "documentation_revision": self.documentation_revision,
            "association": (
                {
                    "provenance": self.association_provenance,
                    "evidence_id": self.association_evidence_id,
                }
                if self.association_provenance is not None
                else None
            ),
            "documentation_ref_required": self.documentation_ref_required,
            "known_documentation_refs": [
                item.to_dict() for item in self.known_documentation_refs
            ],
            "accepted_lineage": (
                self.accepted_lineage.to_dict() if self.accepted_lineage is not None else None
            ),
        }


@dataclass(frozen=True)
class ArchitectureContextCatalog:
    default_context_id: str
    contexts: tuple[ArchitectureContextSelection, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "default_context_id": self.default_context_id,
            "contexts": [context.to_dict() for context in self.contexts],
        }


@dataclass(frozen=True)
class _Candidate:
    code_revision: str | None
    documentation_revision: str
    provenance: Literal["review", "promotion", "accepted_lineage"]
    evidence_id: str
    lineage: str | None = None


def architecture_context_catalog(
    project: ProjectContext,
    session_target: Path,
) -> ArchitectureContextCatalog:
    """Describe the session target first, followed by valid registered worktrees."""

    known = _known_checkouts(project, session_target)
    candidates = (
        ()
        if project.architecture_repository.root.resolve()
        == project.target.root.resolve()
        else _recorded_candidates(project)
    )
    contexts = tuple(
        _resolve_known_context(project, context, candidates=candidates)
        for context in known
    )
    return ArchitectureContextCatalog(known[0].context_id, contexts)


def resolve_architecture_context(
    project: ProjectContext,
    session_target: Path,
    context_id: str | None = None,
    *,
    documentation_ref_id: str | None = None,
) -> ArchitectureContextSelection:
    """Resolve one known checkout and, where possible, its exact documentation commit.

    ``None`` selects the War Room session target.  A split-repository selection
    is automatic only when all exact evidence for that code commit agrees.  An
    explicit documentation choice must be one of the opaque IDs returned by
    this resolver; a raw revision, branch, or path is rejected.
    """

    contexts = _known_checkouts(project, session_target)
    selected_id = context_id or contexts[0].context_id
    try:
        context = next(item for item in contexts if item.context_id == selected_id)
    except StopIteration as exc:
        raise ArchitectureBrowsingError(
            "unknown_context", "architecture context is not registered for this session"
        ) from exc

    return _resolve_known_context(
        project,
        context,
        documentation_ref_id=documentation_ref_id,
    )


def _resolve_known_context(
    project: ProjectContext,
    context: ArchitectureCodeContext,
    *,
    documentation_ref_id: str | None = None,
    candidates: tuple[_Candidate, ...] | None = None,
) -> ArchitectureContextSelection:
    """Bind a previously authorized context to its documentation evidence."""

    docs = project.architecture_repository
    if docs.root.resolve() == project.target.root.resolve():
        if documentation_ref_id is not None:
            raise ArchitectureBrowsingError(
                "documentation_ref_not_allowed",
                "colocated architecture documentation is pinned to the code commit",
            )
        return ArchitectureContextSelection(
            context,
            project.architecture_destination,
            project.target.repository_key,
            context.revision,
            docs.repository_key,
            context.revision,
            "colocated",
            None,
            False,
            (),
        )

    candidates = candidates if candidates is not None else _recorded_candidates(project)
    known_refs = _known_documentation_refs(docs, candidates)
    exact = [item for item in candidates if item.code_revision == context.revision]
    exact_by_revision: dict[str, list[_Candidate]] = {}
    for item in exact:
        if _commit_exists(docs.root, item.documentation_revision):
            exact_by_revision.setdefault(item.documentation_revision, []).append(item)

    accepted = _best_accepted_ref(docs, exact)
    if documentation_ref_id is not None:
        chosen = next(
            (item for item in known_refs if item.ref_id == documentation_ref_id), None
        )
        if chosen is None:
            raise ArchitectureBrowsingError(
                "unknown_documentation_ref",
                "documentation ref is not recorded for this project",
            )
        return ArchitectureContextSelection(
            context,
            project.architecture_destination,
            project.target.repository_key,
            context.revision,
            docs.repository_key,
            chosen.revision,
            "user_selected",
            chosen.ref_id,
            False,
            known_refs,
            accepted,
        )

    if len(exact_by_revision) == 1:
        revision, evidence = next(iter(exact_by_revision.items()))
        best = min(evidence, key=lambda item: _provenance_rank(item.provenance))
        return ArchitectureContextSelection(
            context,
            project.architecture_destination,
            project.target.repository_key,
            context.revision,
            docs.repository_key,
            revision,
            best.provenance,
            best.evidence_id,
            False,
            known_refs,
            accepted,
        )

    return ArchitectureContextSelection(
        context,
        project.architecture_destination,
        project.target.repository_key,
        context.revision,
        docs.repository_key,
        None,
        None,
        None,
        True,
        known_refs,
        accepted,
    )


def _known_checkouts(
    project: ProjectContext, session_target: Path
) -> tuple[ArchitectureCodeContext, ...]:
    session = Path(session_target).resolve()
    target = project.target.root.resolve()
    if not _same_repository(session, target):
        raise ArchitectureBrowsingError(
            "invalid_session_target", "War Room target is not the configured target repository"
        )

    rows: list[tuple[Path, ContextKind, str, str | None, str | None]] = [
        (session, "session_target", "Session target", None, None)
    ]
    seen = {session}
    for entry in load_registry_readonly(locate_trunk(target)):
        path = entry.path.resolve()
        if path in seen or not path.is_dir() or not _same_repository(path, target):
            continue
        seen.add(path)
        rows.append((path, "project_worktree", entry.work_id, entry.work_id, entry.branch))

    contexts: list[ArchitectureCodeContext] = []
    for path, kind, label, work_id, registered_branch in rows:
        try:
            revision = _git_text(path, "rev-parse", "--verify", "HEAD^{commit}")
            branch_result = _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
            if (
                kind == "project_worktree"
                and branch is not None
                and branch != registered_branch
            ):
                # A stale or tampered registry row is not a selectable identity.
                continue
            dirty = bool(
                _git_text(path, "status", "--porcelain", "--untracked-files=all")
            )
        except ArchitectureBrowsingError:
            continue
        identity = "session" if kind == "session_target" else f"work:{work_id}:{registered_branch}"
        contexts.append(
            ArchitectureCodeContext(
                _opaque_id("context", project.target.repository_key, identity),
                kind,
                label,
                project.target.repository_key,
                revision,
                branch,
                branch is None,
                dirty,
                work_id,
            )
        )
    if not contexts:
        raise ArchitectureBrowsingError(
            "unavailable_context", "War Room session target has no committed Git revision"
        )
    return tuple(contexts)


def _recorded_candidates(project: ProjectContext) -> tuple[_Candidate, ...]:
    store = ArchitectureReviewStore(project)
    state = store._read()  # validated durable schema; this resolver never edits it
    candidates: list[_Candidate] = []

    units = {
        unit_id: ArchitectureReviewUnit.from_dict(value)
        for unit_id, value in state["review_units"].items()
    }
    documentation_key = project.architecture_repository.repository_key
    for lineage_rows in state["lineages"].values():
        for value in lineage_rows:
            lineage = AcceptedLineage.from_dict(value)
            unit = units.get(lineage.accepted_review_unit_id)
            if (
                unit is None
                or unit.documentation_repository_role
                != project.architecture_destination
                or unit.documentation_repository_key != documentation_key
            ):
                continue
            candidates.append(
                _Candidate(
                    lineage.accepted_code_head,
                    lineage.accepted_documentation_head,
                    "accepted_lineage",
                    lineage.pointer_id,
                    lineage.lineage_key,
                )
            )
    for value in state["promotions"].values():
        journal = PromotionJournal.from_dict(value)
        if (
            journal.documentation_repository_role
            != project.architecture_destination
            or journal.documentation_repository_key != documentation_key
        ):
            continue
        pairs = [
            (journal.heads.expected_code_head, journal.heads.expected_documentation_head),
            (
                journal.heads.incoming_implementation_commit,
                journal.heads.incoming_documentation_commit,
            ),
        ]
        if (
            journal.code.observed_resulting_head is not None
            and journal.documentation.observed_resulting_head is not None
        ):
            pairs.append(
                (
                    journal.code.observed_resulting_head,
                    journal.documentation.observed_resulting_head,
                )
            )
        for code, documentation in pairs:
            candidates.append(
                _Candidate(
                    code,
                    documentation,
                    "promotion",
                    journal.operation_id,
                    journal.lineage_key,
                )
            )

    receipt_state = _read_receipt_state(project)
    for values in receipt_state.values():
        for value in values:
            receipt = ReconciliationReceipt.from_dict(value)
            if receipt.state != "reconciled" or receipt.accepted_review_unit_id is None:
                continue
            unit = units.get(receipt.accepted_review_unit_id)
            if (
                unit is None
                or unit.documentation_repository_role
                != project.architecture_destination
                or unit.documentation_repository_key != documentation_key
            ):
                continue
            revisions = {
                design.after.reference.revision
                for design in (*receipt.leaf_designs, *receipt.ancestor_designs)
                if design.after.reference.destination_repository_key
                == unit.documentation_repository_key
            }
            if len(revisions) != 1:
                continue
            documentation = next(iter(revisions))
            for code in receipt.implementation_revisions:
                candidates.append(
                    _Candidate(
                        code,
                        documentation,
                        "review",
                        receipt.accepted_review_unit_id,
                        receipt.integration_lineage,
                    )
                )

    # Review units are also authoritative inventories of known documentation
    # commits, even though they do not alone associate one with a code commit.
    for unit in units.values():
        if (
            unit.documentation_repository_role != project.architecture_destination
            or unit.documentation_repository_key != documentation_key
        ):
            continue
        revisions = {unit.plan.revision, unit.design.reference.revision}
        if unit.proposed_model is not None:
            revisions.add(unit.proposed_model.contract.reference.revision)
            revisions.update(
                source.reference.revision for source in unit.proposed_model.sources
            )
        for revision in revisions:
            candidates.append(
                _Candidate(
                    None,
                    revision,
                    "review",
                    unit.review_unit_id,
                    unit.integration_lineage,
                )
            )
    return tuple(candidates)


def _read_receipt_state(project: ProjectContext) -> dict[str, list[object]]:
    from cascade.workspace.reconciliation import ReconciliationReceiptStore

    state = ReconciliationReceiptStore(project)._read()
    return state["receipts"]


def _known_documentation_refs(
    repository: RepositoryContext, candidates: tuple[_Candidate, ...]
) -> tuple[KnownDocumentationRef, ...]:
    grouped: dict[str, list[_Candidate]] = {}
    for item in candidates:
        if _commit_exists(repository.root, item.documentation_revision):
            grouped.setdefault(item.documentation_revision, []).append(item)
    refs = []
    for revision, evidence in grouped.items():
        best = min(evidence, key=lambda item: _provenance_rank(item.provenance))
        refs.append(
            KnownDocumentationRef(
                _opaque_id("documentation", repository.repository_key, revision),
                repository.repository_key,
                revision,
                best.provenance,
                best.evidence_id,
                best.lineage,
            )
        )
    return tuple(sorted(refs, key=lambda item: (item.revision, item.ref_id)))


def _best_accepted_ref(
    repository: RepositoryContext, candidates: list[_Candidate]
) -> KnownDocumentationRef | None:
    accepted = [
        item
        for item in candidates
        if item.provenance == "accepted_lineage"
        and _commit_exists(repository.root, item.documentation_revision)
    ]
    if not accepted:
        return None
    item = accepted[-1]
    return KnownDocumentationRef(
        _opaque_id("documentation", repository.repository_key, item.documentation_revision),
        repository.repository_key,
        item.documentation_revision,
        "accepted_lineage",
        item.evidence_id,
        item.lineage,
    )


def _provenance_rank(value: str) -> int:
    return {"accepted_lineage": 0, "promotion": 1, "review": 2}.get(value, 9)


def _same_repository(left: Path, right: Path) -> bool:
    try:
        left_common = Path(_git_text(left, "rev-parse", "--git-common-dir"))
        right_common = Path(_git_text(right, "rev-parse", "--git-common-dir"))
    except ArchitectureBrowsingError:
        return False
    if not left_common.is_absolute():
        left_common = (left / left_common).resolve()
    if not right_common.is_absolute():
        right_common = (right / right_common).resolve()
    return left_common.resolve() == right_common.resolve()


def _commit_exists(root: Path, revision: str) -> bool:
    return _git(root, "cat-file", "-e", f"{revision}^{{commit}}").returncode == 0


def _git_text(root: Path, *args: str) -> str:
    result = _git(root, *args)
    if result.returncode != 0:
        raise ArchitectureBrowsingError(
            "git_context_unavailable", "known Git context is unavailable"
        )
    return result.stdout.strip()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _opaque_id(kind: str, repository_key: str, identity: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{repository_key}\0{identity}".encode()).hexdigest()
    return f"{kind}-{digest[:32]}"
