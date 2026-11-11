"""Explicit, revision-pinned documentation context for C4 selections."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.workspace import (
    C4ContextAssociation,
    C4ContextSelection,
    C4DocumentationEvidence,
    ContextDocument,
    DesignContext,
    MAX_CONTEXT_ASSOCIATIONS,
    PinnedContextRevision,
    PinnedSourceSection,
    WorkspaceError,
    resolve_c4_documentation_context,
    review_documentation_evidence,
    snapshot_documentation_evidence,
)

DOC_REVISION = "d" * 40
OLD_REVISION = "e" * 40
CODE_REVISION = "c" * 40


def _source(
    section: str | None = "requirements/queue",
    *,
    revision: str = DOC_REVISION,
    path: str = "cascade/workspace/DESIGN.md",
) -> PinnedSourceSection:
    return PinnedSourceSection(
        "architecture-docs", revision, Path(path), section
    )


def _document(
    identifier: str,
    kind: str = "requirement",
    *,
    revision: str = DOC_REVISION,
) -> ContextDocument:
    return ContextDocument(
        identifier,
        kind,  # type: ignore[arg-type]
        f"Title for {identifier}",
        _source(f"{kind}s/{identifier.lower()}", revision=revision),
    )


def _association(
    kind: str,
    semantic_id: str,
    document_id: str,
    document_kind: str = "requirement",
    *,
    view_key: str | None = None,
) -> C4ContextAssociation:
    return C4ContextAssociation(
        kind,  # type: ignore[arg-type]
        semantic_id,
        document_id,
        document_kind,  # type: ignore[arg-type]
        "explicit_mapping",
        "architecture/document-context.json@" + DOC_REVISION,
        view_key=view_key,
    )


def test_exact_many_to_many_links_do_not_bleed_from_labels_or_other_targets() -> None:
    requirement = _document("REQ-QUEUE-001")
    decision = _document("DEC-QUEUE-002", "decision")
    owner = DesignContext(Path("cascade/workspace"), Path("cascade/workspace"), _source(None))
    broader = DesignContext(Path("cascade"), Path("cascade"), _source(None, path="cascade/DESIGN.md"))
    evidence = C4DocumentationEvidence(
        "snapshot",
        "architecture-snapshot-1",
        (PinnedContextRevision("architecture-docs", DOC_REVISION),),
        (requirement, decision),
        (
            _association("element", "element.queue", requirement.document_id),
            _association("element", "element.queue", decision.document_id, "decision"),
            _association("relationship", "relationship.enqueues", requirement.document_id),
            # Similar display text is intentionally irrelevant to semantic matching.
            _association("element", "element.queue-worker", requirement.document_id),
        ),
        (owner,),
        (broader,),
    )

    selected = resolve_c4_documentation_context(
        evidence,
        C4ContextSelection("element", "element.queue", view_key="containers"),
    )

    assert selected.mapping_state == "mapped"
    assert [(row.document_id, row.kind) for row in selected.explicit_links] == [
        ("DEC-QUEUE-002", "decision"),
        ("REQ-QUEUE-001", "requirement"),
    ]
    assert selected.owner_context == (owner,)
    assert selected.broader_index == (broader,)
    assert selected.to_dict()["explicit_target_links"][0]["source"]["section"] == (
        "decisions/dec-queue-002"
    )

    unmapped = resolve_c4_documentation_context(
        evidence, C4ContextSelection("element", "Queue")
    )
    assert unmapped.mapping_state == "unmapped"
    assert unmapped.explicit_links == ()
    # Owning context is still useful, but is not represented as target coverage.
    assert unmapped.owner_context == (owner,)


def test_missing_and_out_of_snapshot_references_remain_visible() -> None:
    stale = _document("REQ-OLD-001", revision=OLD_REVISION)
    explicitly_missing = ContextDocument(
        "DEC-GONE-001", "decision", "Removed decision", None,
        state="missing", reason="source_blob_missing",
    )
    evidence = C4DocumentationEvidence(
        "snapshot",
        "architecture-snapshot-2",
        (PinnedContextRevision("architecture-docs", DOC_REVISION),),
        (stale, explicitly_missing),
        (
            _association("relationship", "relationship.calls", stale.document_id),
            _association("relationship", "relationship.calls", explicitly_missing.document_id, "decision"),
            _association("relationship", "relationship.calls", "REQ-UNKNOWN-001"),
        ),
    )

    result = resolve_c4_documentation_context(
        evidence, C4ContextSelection("relationship", "relationship.calls")
    )

    by_id = {row.document_id: row for row in result.explicit_links}
    assert (by_id["REQ-OLD-001"].state, by_id["REQ-OLD-001"].reason) == (
        "stale", "revision_not_in_scope"
    )
    assert (by_id["DEC-GONE-001"].state, by_id["DEC-GONE-001"].reason) == (
        "missing", "source_blob_missing"
    )
    assert (by_id["REQ-UNKNOWN-001"].state, by_id["REQ-UNKNOWN-001"].reason) == (
        "missing", "reference_missing"
    )


def test_view_scoping_is_exact_and_aggregates_reviewed_and_mapping_provenance() -> None:
    document = _document("REQ-SHARED-001")
    global_edge = _association("element", "element.api", document.document_id)
    scoped_edge = _association(
        "element", "element.api", document.document_id, view_key="containers"
    )
    evidence = C4DocumentationEvidence(
        "review",
        "review-1",
        (PinnedContextRevision("architecture-docs", DOC_REVISION),),
        (document,),
        (
            global_edge,
            scoped_edge,
            replace(
                global_edge,
                provenance="reviewed_association",
                evidence_id="architecture-review-1",
            ),
        ),
    )

    result = resolve_c4_documentation_context(
        evidence,
        C4ContextSelection("element", "element.api", view_key="components"),
    )

    assert len(result.explicit_links) == 1
    assert result.explicit_links[0].provenance == (
        {
            "relation": "explicit_mapping",
            "evidence_id": global_edge.evidence_id,
            "selection_kind": "element",
            "semantic_id": "element.api",
        },
        {
            "relation": "reviewed_association",
            "evidence_id": "architecture-review-1",
            "selection_kind": "element",
            "semantic_id": "element.api",
        },
    )


def test_review_builder_only_promotes_review_citations_to_recorded_views() -> None:
    unit = SimpleNamespace(
        review_unit_id="architecture-review-reviewed",
        requirement_citations=("REQ-7",),
        decision_citations=("ADR-4",),
        view_citations=("containers", "components"),
        code_directory=Path("cascade/workspace"),
        design_owner_directory=Path("cascade/workspace"),
        plan=SimpleNamespace(repository_key="plans", revision="a" * 40),
        design=SimpleNamespace(
            reference=SimpleNamespace(
                destination_repository_key="architecture-docs",
                revision=DOC_REVISION,
                repository_path=Path("cascade/workspace/DESIGN.md"),
            ),
            content_digest="f" * 64,
        ),
    )
    requirement = _document("REQ-7")
    decision = _document("ADR-4", "decision")

    evidence = review_documentation_evidence(unit, (requirement, decision))

    containers = resolve_c4_documentation_context(
        evidence, C4ContextSelection("view", "containers")
    )
    assert containers.explicit_links == ()
    assert {row.document_id for row in containers.view_links} == {"REQ-7", "ADR-4"}
    assert all(
        row.provenance[0]["relation"] == "reviewed_association"
        for row in containers.view_links
    )
    element = resolve_c4_documentation_context(
        evidence, C4ContextSelection("element", "element.containers")
    )
    assert element.mapping_state == "unmapped"
    assert element.explicit_links == ()
    assert evidence.owner_context[0].source.revision == DOC_REVISION


def test_split_snapshot_uses_recorded_document_revision_not_tracking_head() -> None:
    descriptor = {
        "repositories": {"code": "target-project", "documentation": "architecture-docs"},
        "revisions": {"code": CODE_REVISION, "documentation": DOC_REVISION},
        "mapping": {
            "repository_key": "target-project",
            "revision": CODE_REVISION,
            "path": "architecture/design-mappings.json",
        },
        "association": {"provenance": "promotion", "evidence_id": "promotion-7"},
    }
    current = _document("REQ-CURRENT-001")
    tracking_head = _document("REQ-HEAD-001", revision=OLD_REVISION)
    associations = (
        _association("view", "system-context", current.document_id),
        _association("view", "system-context", tracking_head.document_id),
    )

    evidence = snapshot_documentation_evidence(
        "architecture-snapshot-split", descriptor, (current, tracking_head), associations
    )
    result = resolve_c4_documentation_context(
        evidence, C4ContextSelection("view", "system-context")
    )

    assert {(row.repository_key, row.revision) for row in result.pinned_revisions} == {
        ("target-project", CODE_REVISION),
        ("architecture-docs", DOC_REVISION),
    }
    states = {row.document_id: row.state for row in result.view_links}
    assert states == {"REQ-CURRENT-001": "available", "REQ-HEAD-001": "stale"}
    assert result.mapping_source == PinnedSourceSection(
        "target-project", CODE_REVISION, Path("architecture/design-mappings.json")
    )
    assert dict(result.documentation_association) == {
        "provenance": "promotion",
        "evidence_id": "promotion-7",
    }


def test_target_links_remain_distinct_from_enclosing_view_links() -> None:
    target = _document("REQ-TARGET-001")
    view = _document("REQ-VIEW-001")
    evidence = C4DocumentationEvidence(
        "snapshot",
        "architecture-snapshot-context",
        (PinnedContextRevision("architecture-docs", DOC_REVISION),),
        (target, view),
        (
            _association("element", "element.api", target.document_id),
            _association("view", "containers", view.document_id),
        ),
    )

    result = resolve_c4_documentation_context(
        evidence,
        C4ContextSelection("element", "element.api", view_key="containers"),
    )

    assert [row.document_id for row in result.explicit_links] == ["REQ-TARGET-001"]
    assert [row.document_id for row in result.view_links] == ["REQ-VIEW-001"]
    assert result.mapping_state == "mapped"

    unmapped_target = resolve_c4_documentation_context(
        evidence,
        C4ContextSelection("element", "element.worker", view_key="containers"),
    )
    assert unmapped_target.mapping_state == "unmapped"
    assert unmapped_target.explicit_links == ()
    assert [row.document_id for row in unmapped_target.view_links] == ["REQ-VIEW-001"]


def test_context_input_is_bounded_before_resolution() -> None:
    edge = _association("view", "context", "REQ-1")
    with pytest.raises(WorkspaceError, match="bounded limit"):
        C4DocumentationEvidence(
            "snapshot",
            "architecture-snapshot-large",
            (PinnedContextRevision("architecture-docs", DOC_REVISION),),
            (),
            tuple(replace(edge, document_id=f"REQ-{index}") for index in range(MAX_CONTEXT_ASSOCIATIONS + 1)),
        )
