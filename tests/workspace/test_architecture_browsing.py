"""Known-context and exact split-documentation architecture resolution."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import cascade.workspace.architecture_browsing as browsing
from cascade.workspace.architecture_browsing import (
    ArchitectureBrowsingError,
    architecture_context_catalog,
    resolve_architecture_context,
)
from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
from cascade.workspace.architecture import (
    create_architecture_artifact_ref,
    resolve_design_ownership,
)
from cascade.workspace.architecture_review import (
    ArchitectureReviewStore,
    PinnedArchitectureArtifact,
)
from cascade.workspace.types import ProjectContext
from tests.support import make_repo
from tests.workspace.test_architecture_review import _review_repository, _unit


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _commit(root: Path, name: str, body: str) -> str:
    (root / name).write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", f"add {name}"], cwd=root, check=True)
    return _git(root, "rev-parse", "HEAD")


def _registered_contexts(tmp_path: Path) -> tuple[Path, ProjectContext, str, str]:
    root = make_repo(tmp_path)
    main_revision = _commit(root, "main.txt", "main\n")
    worktree = root / ".cascade" / "worktrees" / "feat_feat_001"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-qb", "feat/feat_001", str(worktree)],
        cwd=root,
        check=True,
    )
    branch_revision = _commit(worktree, "branch.txt", "branch\n")
    save_registry(
        root,
        [
            IntegrationWorktree(
                "feature", "feat_001", "feat/feat_001", worktree, main_revision
            )
        ],
    )
    return root, ProjectContext.colocated(root), main_revision, branch_revision


def test_catalog_defaults_to_session_and_reports_second_detached_dirty_context(
    tmp_path: Path,
) -> None:
    root, project, main_revision, branch_revision = _registered_contexts(tmp_path)
    worktree = root / ".cascade" / "worktrees" / "feat_feat_001"
    subprocess.run(["git", "checkout", "--detach", branch_revision], cwd=worktree, check=True)
    (worktree / "dirty.txt").write_text("not committed\n", encoding="utf-8")

    catalog = architecture_context_catalog(project, root)

    assert len(catalog.contexts) == 2
    default, second = catalog.contexts
    assert catalog.default_context_id == default.context.context_id
    assert default.context.kind == "session_target"
    assert default.context.revision == main_revision
    assert default.context.branch == "main"
    assert default.documentation_revision == main_revision
    assert second.context.kind == "project_worktree"
    assert second.context.revision == branch_revision
    assert second.context.branch is None
    assert second.context.detached is True
    assert second.context.dirty is True
    # Dirty bytes are never represented as an architecture revision.
    assert second.documentation_revision == branch_revision


def test_context_selection_rejects_paths_and_unregistered_checkout_ids(tmp_path: Path) -> None:
    root, project, _, _ = _registered_contexts(tmp_path)

    with pytest.raises(ArchitectureBrowsingError) as raised:
        resolve_architecture_context(project, root, str(root))

    assert raised.value.code == "unknown_context"


def _split_project(tmp_path: Path) -> tuple[ProjectContext, str, str, str]:
    target_parent = tmp_path / "target-parent"
    tracking_parent = tmp_path / "tracking-parent"
    target_parent.mkdir()
    tracking_parent.mkdir()
    target = make_repo(target_parent)
    tracking = make_repo(tracking_parent)
    code_revision = _commit(target, "code.txt", "code\n")
    old_docs = _commit(tracking, "architecture.txt", "old\n")
    new_docs = _commit(tracking, "architecture.txt", "new\n")
    return (
        ProjectContext.split(target, tracking, architecture_destination="tracking"),
        code_revision,
        old_docs,
        new_docs,
    )


def test_split_exact_association_wins_and_accepted_lineage_is_distinguished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, code_revision, old_docs, new_docs = _split_project(tmp_path)
    monkeypatch.setattr(
        browsing,
        "_recorded_candidates",
        lambda _project: (
            browsing._Candidate(code_revision, old_docs, "review", "review-1", "epic:e1"),
            browsing._Candidate(code_revision, new_docs, "accepted_lineage", "lineage-1", "epic:e1"),
        ),
    )

    selection = resolve_architecture_context(project, project.target.root)

    assert selection.state == "documentation_ref_required"
    assert selection.documentation_revision is None
    assert {item.revision for item in selection.known_documentation_refs} == {
        old_docs,
        new_docs,
    }
    assert selection.accepted_lineage is not None
    assert selection.accepted_lineage.revision == new_docs
    assert selection.accepted_lineage.provenance == "accepted_lineage"

    selected = resolve_architecture_context(
        project,
        project.target.root,
        documentation_ref_id=selection.accepted_lineage.ref_id,
    )
    assert selected.documentation_revision == new_docs
    assert selected.association_provenance == "user_selected"
    assert selected.association_evidence_id == selection.accepted_lineage.ref_id


def test_split_unique_association_resolves_but_missing_never_uses_tracking_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, code_revision, old_docs, new_docs = _split_project(tmp_path)
    monkeypatch.setattr(
        browsing,
        "_recorded_candidates",
        lambda _project: (
            browsing._Candidate(code_revision, old_docs, "promotion", "promotion-1"),
            browsing._Candidate(None, new_docs, "review", "review-2"),
        ),
    )

    associated = resolve_architecture_context(project, project.target.root)
    assert associated.state == "ready"
    assert associated.documentation_revision == old_docs
    assert associated.association_provenance == "promotion"

    monkeypatch.setattr(
        browsing,
        "_recorded_candidates",
        lambda _project: (browsing._Candidate(None, old_docs, "review", "review-2"),),
    )
    missing = resolve_architecture_context(project, project.target.root)
    assert missing.state == "documentation_ref_required"
    assert missing.documentation_revision is None
    assert _git(project.tracking.root, "rev-parse", "HEAD") == new_docs
    assert [item.revision for item in missing.known_documentation_refs] == [old_docs]

    with pytest.raises(ArchitectureBrowsingError) as raised:
        resolve_architecture_context(
            project,
            project.target.root,
            documentation_ref_id="documentation-not-recorded",
        )
    assert raised.value.code == "unknown_documentation_ref"


def test_split_accepted_lineage_store_provides_exact_association(
    tmp_path: Path,
) -> None:
    colocated, plan, design, model = _review_repository(tmp_path)
    tracking_parent = tmp_path / "tracking-parent"
    tracking_parent.mkdir()
    tracking = make_repo(tracking_parent)
    _commit(tracking, "README.md", "# Tracking\n")
    project = ProjectContext.split(
        colocated.target.root, tracking, architecture_destination="tracking"
    )
    resolve_design_ownership(project, ".")
    project.design_path().parent.mkdir(parents=True, exist_ok=True)
    project.design_path().write_text("# Split design\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tracking, check=True)
    subprocess.run(["git", "commit", "-qm", "architecture"], cwd=tracking, check=True)
    documentation_revision = _git(tracking, "rev-parse", "HEAD")
    code_revision = _git(project.target.root, "rev-parse", "HEAD")
    split_design = PinnedArchitectureArtifact(
        create_architecture_artifact_ref(project, ".", owning_work="feat_034_003"),
        hashlib.sha256(project.design_path().read_bytes()).hexdigest(),
    )
    proposal = replace(
        _unit(colocated, plan, design, model),
        documentation_repository_key=project.architecture_repository.repository_key,
        documentation_repository_role="tracking",
        design=split_design,
        proposed_model=None,
        view_citations=(),
        architecture_impact="no_diagram_change",
    )
    store = ArchitectureReviewStore(project)
    store.save(proposal)
    accepted = store.accept(
        proposal.review_unit_id,
        accepted_code_head=code_revision,
        accepted_documentation_head=documentation_revision,
        expected_generation=None,
    )

    selection = resolve_architecture_context(project, project.target.root)

    assert selection.state == "ready"
    assert selection.documentation_revision == documentation_revision
    assert selection.association_provenance == "accepted_lineage"
    assert selection.association_evidence_id == accepted.pointer_id
    assert selection.mapping_revision == code_revision
