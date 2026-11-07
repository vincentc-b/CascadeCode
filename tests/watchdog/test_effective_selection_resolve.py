"""Complete effective-selection scope, provenance, and fingerprint behavior."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from cascade.agent.capability_contract import EffectiveSelection, SelectionIssue
from cascade.board.types import WorkDoc
from cascade.watchdog.model_resolve import resolve_effective_selections
from tests.support import add_doc, make_repo


def _write_config(root: Path) -> None:
    (root / "cascade.toml").write_text(
        """
[providers]
default = "cursor"

[providers.cursor]
epic = "epic-default"
feature = "feature-default"
task = "task-default"

[providers.cursor.roles]
feature_architect = "architect-default"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _doc(root: Path, *, tier: str, work_id: str) -> WorkDoc:
    seed = add_doc(root, id="epic_999", title="Selection", tier="epic")
    parent = None
    if tier == "feature":
        parent = "epic_001"
    elif tier == "task":
        parent = "feat_001"
    path = root / "docs" / f"{tier}s" / "1_backlog" / f"{work_id}_selection.md"
    return WorkDoc(
        meta=replace(
            seed.meta,
            id=work_id,
            tier=tier,  # type: ignore[arg-type]
            parent=parent,
            path=path,
        ),
        body=seed.body,
        sha=seed.sha,
    )


def test_epic_resolves_all_roles_with_precedence_and_provenance(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _write_config(root)
    doc = _doc(root, tier="epic", work_id="epic_001")
    doc.meta = replace(
        doc.meta,
        provider="cursor",
        model="legacy-model",
        models={
            "epic_manager": "manager-pin",
            "feature_lead": "lead-pin",
            "swe": "swe-pin",
        },
        reasoning={"epic_manager": "high"},
        flex_mode=True,
    )

    batch = resolve_effective_selections(
        doc,
        root=root,
        provider_reasoning_defaults={("cursor", "legacy-model"): "medium"},
    )

    assert batch.complete
    assert tuple(item.role for item in batch.roles) == (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert [item.model_id for item in batch.selections] == [
        "manager-pin",
        "legacy-model",
        "lead-pin",
        "legacy-model",
        "swe-pin",
    ]
    manager = batch.selections[0]
    architect = batch.selections[1]
    assert manager.field_sources["model_id"].kind == "document-role"
    assert architect.field_sources["model_id"].kind == "document"
    assert manager.reasoning_effective == "high"
    assert architect.reasoning_effective == "medium"
    assert all(item.selection_fingerprint == batch.selection_fingerprint for item in batch.selections)


def test_feature_scope_includes_effective_swe_and_project_precedence(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _write_config(root)
    doc = _doc(root, tier="feature", work_id="feat_001")
    doc.meta = replace(
        doc.meta,
        models={"feature_lead": "lead-pin"},
    )
    parent = WorkDoc(
        meta=replace(
            doc.meta,
            id="epic_001",
            tier="epic",
            parent=None,
            path=root / "docs/epics/2_active/epic_001_parent.md",
            models={"swe": "epic-swe-pin"},
        ),
        body=doc.body,
        sha="parent-revision-1",
    )

    batch = resolve_effective_selections(doc, root=root, parent_doc=parent)

    assert tuple(item.role for item in batch.roles) == (
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert [item.model_id for item in batch.selections] == [
        "lead-pin",
        "architect-default",
        "epic-swe-pin",
    ]
    assert batch.selections[1].field_sources["model_id"].kind == "project-role"
    assert batch.selections[2].field_sources["model_id"].document_path == (
        "docs/epics/2_active/epic_001_parent.md"
    )
    assert batch.selections[2].field_sources["model_id"].stamping_rule == (
        "feature_backend_from_epic"
    )

    changed_parent = replace(parent, sha="parent-revision-2")
    changed = resolve_effective_selections(doc, root=root, parent_doc=changed_parent)
    assert changed.selection_fingerprint != batch.selection_fingerprint


def test_fingerprint_tracks_reviewed_selection_not_inventory_or_waiver(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _write_config(root)
    doc = _doc(root, tier="task", work_id="task_001")
    doc.meta = replace(doc.meta, provider="cursor", models={"swe": "task-pin"})

    first = resolve_effective_selections(
        doc,
        root=root,
        provider_reasoning_defaults={("cursor", "task-pin"): "low"},
    )
    waived = resolve_effective_selections(
        doc,
        root=root,
        provider_reasoning_defaults={("cursor", "task-pin"): "high"},
        effective_flex_mode=True,
    )
    revised = resolve_effective_selections(
        doc,
        root=root,
        document_revision="new-document-revision",
    )

    assert first.selection_fingerprint == waived.selection_fingerprint
    assert first.selections[0].reasoning_effective == "low"
    assert waived.selections[0].reasoning_effective == "high"
    assert first.selections[0].effective_flex_mode is False
    assert waived.selections[0].effective_flex_mode is True
    assert revised.selection_fingerprint != first.selection_fingerprint


def test_blank_explicit_value_and_resolver_exception_are_safe_role_issues(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path)
    _write_config(root)
    doc = _doc(root, tier="task", work_id="task_001")
    doc.meta = replace(doc.meta, models={"swe": "  "})

    malformed = resolve_effective_selections(doc, root=root)
    assert not malformed.complete
    assert malformed.issues[0].reason_code == "malformed_configuration"
    assert malformed.issues[0].provider == "cursor"
    assert malformed.issues[0].message == "Agent configuration is malformed"

    doc.meta = replace(doc.meta, models={"swe": "valid"})

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret provider detail")

    monkeypatch.setattr("cascade.watchdog.model_resolve.resolve_backend", explode)
    failed = resolve_effective_selections(doc, root=root)
    issue = failed.roles[0]
    assert isinstance(issue, SelectionIssue)
    assert issue.reason_code == "malformed_configuration"
    assert "secret" not in issue.message


def test_missing_configuration_returns_issue_and_stable_diagnostic_fingerprint(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    doc = _doc(root, tier="task", work_id="task_001")

    first = resolve_effective_selections(doc, root=root)
    second = resolve_effective_selections(doc, root=root)

    assert isinstance(first.roles[0], SelectionIssue)
    assert first.roles[0].reason_code == "missing_configuration"
    assert first.selection_fingerprint == second.selection_fingerprint
    assert len(first.selection_fingerprint) == 64
    assert not any(isinstance(item, EffectiveSelection) for item in first.roles)
