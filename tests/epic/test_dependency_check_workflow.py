"""Installed software needs verification, not an installation approval ceremony."""
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool, mcp_tool_catalog
from cascade.epic.dependency_approvals import AuthenticatedHuman, approve_dependency_installations
from cascade.epic.dependency_bootstrap import read_bootstrap
from cascade.epic.dependency_evidence import CheckAdmission, CheckOperationKind, read_dependency_check_history
from cascade.epic.dependency_manifests import DependencyManifestDraft, write_dependency_manifest
from cascade.epic.dependency_checks import run_dependency_check
from cascade.epic.local_dependency_executor import local_environment_identity
from tests.epic.test_dependency_resume import dependency
from tests.support import add_doc, make_repo


def prepare(tmp_path):
    from cascade.workspace.integration_worktree import create_integration_worktree
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    create_integration_worktree("epic", "epic_001", branch="epic/epic_001", base_ref="HEAD", trunk=root)
    target = local_environment_identity(root)
    entry = replace(dependency(target),
                    operation="mkdir -p .tools && touch .tools/ready",
                    verification_recipe="test -f .tools/ready && printf 'tool 1.2.3 verified'",
                    feasibility_proof_requirements=(), feasibility_proof_references=())
    draft = DependencyManifestDraft(target, None, False, (entry,))
    write_dependency_manifest("epic_001", draft, root=root, expected_revision=0)
    return root, entry, draft


def test_registered_check_validates_existing_installation_without_bootstrap_or_approval(tmp_path):
    root, entry, _ = prepare(tmp_path)
    (root / ".tools").mkdir()
    (root / ".tools/ready").touch()
    assert read_bootstrap("epic_001", root=root) is None
    from cascade.agent.mcp_wrappers import build_planning_custom_tools
    from cascade.agent.planning_sandbox import PlanningSandbox
    sandbox = PlanningSandbox(scratch_dir=tmp_path / "scratch", repo_root=root, tier="epic", scope_id="epic_001", role="epic_manager")
    names = list(build_planning_custom_tools(sandbox, ToolEffectCollector()))
    catalog = mcp_tool_catalog("epic", names)
    assert any(row["name"] == "run_dependency_check" for row in catalog)
    result = dispatch_planning_tool("epic", "run_dependency_check", {},
        scope_id="epic_001", repo_root=root, role="epic_manager", collector=ToolEffectCollector())
    assert result["check"]["ready"]
    row = result["software_dependency_status"]["dependencies"][0]
    assert row["installation_approval"]["state"] == "missing"
    assert row["evidence"]["state"] == "current"
    assert read_bootstrap("epic_001", root=root).authorization is None
    admissions = [event for event in read_dependency_check_history("epic_001", root=root) if isinstance(event, CheckAdmission)]
    assert [event.operation_kind for event in admissions] == [CheckOperationKind.READ_ONLY]


def test_missing_dependency_requires_exact_approval_then_automatically_installs_and_verifies(tmp_path):
    root, entry, _ = prepare(tmp_path)
    refused = run_dependency_check(epic_id="epic_001", root=root)
    assert not refused["check"]["ready"]
    assert not (root / ".tools/ready").exists()
    approve_dependency_installations("epic_001", (entry.dependency_id,), root=root,
                                    approver=AuthenticatedHuman("operator"))
    accepted = run_dependency_check(epic_id="epic_001", root=root)
    assert accepted["check"]["ready"]
    assert (root / ".tools/ready").exists()
    kinds = [event.operation_kind for event in read_dependency_check_history("epic_001", root=root) if isinstance(event, CheckAdmission)]
    assert kinds == [CheckOperationKind.READ_ONLY, CheckOperationKind.READ_ONLY,
                     CheckOperationKind.INSTALL, CheckOperationKind.READ_ONLY]


def test_check_tool_cannot_supply_approval_or_cross_epic_scope(tmp_path):
    root, _, _ = prepare(tmp_path)
    for args in ({"epic_id": "epic_002"}, {"approval_reference": "made-up"}, {"root": "/tmp"}):
        with pytest.raises(ValueError, match="no arguments"):
            dispatch_planning_tool("epic", "run_dependency_check", args,
                scope_id="epic_001", repo_root=root, role="epic_architect", collector=ToolEffectCollector())
    with pytest.raises(PermissionError):
        dispatch_planning_tool("epic", "run_dependency_check", {},
            scope_id="epic_001", repo_root=root, role="feature_lead", collector=ToolEffectCollector())


def test_manifest_authoring_triggers_checks_without_extra_ping(tmp_path):
    from cascade.epic.dependency_manifest_authoring import write_dependency_manifest as author
    root, entry, draft = prepare(tmp_path)
    (root / ".tools").mkdir()
    (root / ".tools/ready").touch()
    result = author(draft.to_dict(), 1, epic_id="epic_001", root=root)
    assert result["software_dependency_status"]["dependencies"][0]["evidence"]["state"] == "current"


def test_changed_installation_binding_does_not_reuse_old_approval(tmp_path):
    root, entry, draft = prepare(tmp_path)
    approve_dependency_installations("epic_001", (entry.dependency_id,), root=root,
                                    approver=AuthenticatedHuman("operator"))
    changed = replace(entry, operation="mkdir -p .tools && touch .tools/unapproved")
    write_dependency_manifest("epic_001", replace(draft, dependencies=(changed,)), root=root, expected_revision=1)
    result = run_dependency_check(epic_id="epic_001", root=root)
    assert not result["check"]["ready"]
    assert not (root / ".tools/unapproved").exists()
    assert result["software_dependency_status"]["dependencies"][0]["installation_approval"]["state"] == "stale"
    assert all(event.operation_kind is CheckOperationKind.READ_ONLY for event in
               read_dependency_check_history("epic_001", root=root) if isinstance(event, CheckAdmission))
