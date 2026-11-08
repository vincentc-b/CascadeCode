from pathlib import Path
import pytest

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.epic.dependency_manifest_authoring import read_dependency_manifest
from cascade.team_supervision import message_team
from cascade.task.guard import contract_scope_blocker
from tests.epic.test_dependency_manifest_authoring import board, manifest
from tests.support import add_doc


def test_legacy_epic_can_author_manifest_through_role_dispatch(board):
    result = dispatch_planning_tool(
        "epic",
        "write_dependency_manifest",
        {"manifest": manifest(), "expected_revision": 0},
        scope_id="epic_001",
        repo_root=board,
        collector=ToolEffectCollector(),
        role="epic_manager",
    )
    assert result["manifest_revision"] == 1
    assert read_dependency_manifest(epic_id="epic_001", root=board)["manifest"][
        "none_required"
    ]
    with pytest.raises(ValueError):
        dispatch_planning_tool(
            "epic",
            "write_dependency_manifest",
            {"manifest": manifest(), "expected_revision": 1, "epic_id": "epic_999"},
            scope_id="epic_001",
            repo_root=board,
            collector=ToolEffectCollector(),
            role="epic_manager",
        )


@pytest.mark.parametrize("role", [None, "swe", "feature_lead", "boss"])
def test_manifest_dispatch_rejects_non_epic_planners(board, role):
    with pytest.raises(PermissionError):
        dispatch_planning_tool(
            "epic",
            "read_dependency_manifest",
            {},
            scope_id="epic_001",
            repo_root=board,
            collector=ToolEffectCollector(),
            role=role,
        )


def test_direct_family_messages_are_durable_and_deduplicated(board):
    add_doc(
        board,
        id="feat_001",
        tier="feature",
        title="Feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        board,
        id="feat_002",
        tier="feature",
        title="Other",
        status="active",
        parent="epic_001",
    )
    first = message_team(
        "epic_001",
        "Need scope clarification",
        "question-1",
        feature_id="feat_001",
        root=board,
    )
    assert (
        message_team(
            "epic_001",
            "Need scope clarification",
            "question-1",
            feature_id="feat_001",
            root=board,
        )
        == first
    )
    with pytest.raises(PermissionError):
        message_team(
            "feat_002", "unrelated", "question-2", feature_id="feat_001", root=board
        )
    with pytest.raises(ValueError):
        message_team(
            "epic_001", "different", "question-1", feature_id="feat_001", root=board
        )


def test_scope_preflight_only_blocks_explicit_denied_deliverables():
    assert (
        contract_scope_blocker("## Deliverables\n- `docs/features/plan.md`\n")["reason"]
        == "task_scope_denied"
    )
    assert (
        contract_scope_blocker(
            "## Deliverables\n- `docs/features/plan.md`\n- `cascade/source.py`\n"
        )
        is None
    )
    assert contract_scope_blocker("Read docs/features/plan.md for background") is None


def test_manifest_authoring_unblocks_signoffs_approval_and_feature_dispatch(
    board, monkeypatch
):
    from cascade.approvals import approve_epic_plan
    from cascade.board.store import read_doc, write_doc
    from cascade.epic.mint import mint_feature
    from cascade.epic.planning_signoffs import canonical_plan_revision
    from cascade.watchdog.dispatch import dispatch_feature
    from cascade.workspace.doc_root import resolve_doc_worktree
    from tests.support import FEATURE_BODY
    from tests.test_approval_selection_gate import _inventory

    inventory = _inventory("offered")
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    owning = resolve_doc_worktree("epic_001", root=board)
    epic = read_doc("epic_001", root=owning)
    epic.meta.provider = "codex"
    epic.meta.models = {
        role: "offered"
        for role in (
            "epic_manager",
            "epic_architect",
            "feature_lead",
            "feature_architect",
            "swe",
        )
    }
    write_doc(epic, root=owning)
    dispatch_planning_tool(
        "epic",
        "write_dependency_manifest",
        {"manifest": manifest(), "expected_revision": 0},
        scope_id="epic_001",
        repo_root=board,
        collector=ToolEffectCollector(),
        role="epic_manager",
    )
    child = mint_feature(
        "Implement", body_stub=FEATURE_BODY, epic_id="epic_001", root=board
    )
    revision = canonical_plan_revision("epic_001", root=board)
    for role in ("epic_manager", "epic_architect"):
        dispatch_planning_tool(
            "epic",
            "sign_off_plan",
            {"plan_revision": revision},
            scope_id="epic_001",
            repo_root=board,
            collector=ToolEffectCollector(),
            role=role,
        )
    approve_epic_plan("epic_001", root=board, inventory=inventory)
    result = dispatch_feature(child, "human", root=board)
    assert result.ok, result
