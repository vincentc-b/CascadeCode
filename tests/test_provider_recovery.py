"""Provider recovery validates before touching active-item state."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cascade.agent.discovery.inventory import InventoryFreshness, ProviderInventoryItem, ProviderInventoryResult
from cascade.agent.discovery.types import DiscoveredModel, ReasoningCapability
from cascade.board.store import move_doc, read_doc, read_doc_in_worktree, write_doc
from cascade.provider_recovery import ProviderRecoveryRequest, recover_active_item_provider
from cascade.provider_recovery_command import recover_active_item_provider_command
from cascade.task.graph import clear_task_graph_sessions, seed_task_role_models
from cascade.watchdog.model_resolve import resolve_backend
from cascade.workspace.integration_worktree import ensure_integration_worktree
from tests.support import add_doc, make_repo


def _inventory(model: str, *, reasoning: bool = False, flex: bool = False) -> ProviderInventoryResult:
    capability = ReasoningCapability("standard", ("thorough",)) if reasoning else None
    return ProviderInventoryResult(
        providers=(ProviderInventoryItem(
            "codex", "Codex", (DiscoveredModel(id=model, display_name=model, reasoning=capability),),
            supports_flex_mode=flex,
        ),),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 1.0, 1.0),
    )


def _active_task(tmp_path: Path) -> tuple[Path, str]:
    root = make_repo(tmp_path, git=False, models=True)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    task_id = "task_001"
    add_doc(root, id=task_id, title="Task", tier="task", status="active", parent="feat_001")
    task = read_doc(task_id, root=root)
    seed_task_role_models(task_id, swe=resolve_backend("swe", task.meta, root=root), root=root, feature_id="feat_001")
    return root, task_id


def test_invalid_recovery_does_not_mutate_document_or_checkpoint(tmp_path: Path) -> None:
    root, task_id = _active_task(tmp_path)
    before = read_doc(task_id, root=root)
    result = recover_active_item_provider(
        task_id,
        ProviderRecoveryRequest("codex", {"swe": "not-offered"}),
        root=root,
        inventory=_inventory("offered"),
    )
    after = read_doc(task_id, root=root)
    assert result.disposition == "validation_failed"
    assert after.meta.provider == before.meta.provider
    assert after.meta.models == before.meta.models


def test_checkpoint_failure_restores_document_selection(tmp_path: Path, monkeypatch) -> None:
    root, task_id = _active_task(tmp_path)
    before = read_doc(task_id, root=root)
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph

    graph = ensure_task_graph(task_id, root=root, feature_id="feat_001")
    before_pins = dict(graph.get_state(thread_config(task_id)).values["model_ids"])

    def fail(*args, **kwargs) -> None:
        raise OSError("checkpoint unavailable")

    monkeypatch.setattr("cascade.provider_recovery._write_pins", fail)
    result = recover_active_item_provider(
        task_id,
        ProviderRecoveryRequest("codex", {"swe": "offered"}),
        root=root,
        inventory=_inventory("offered"),
    )
    after = read_doc(task_id, root=root)
    assert result.disposition == "rolled_back"
    assert after.meta.provider == before.meta.provider
    assert after.meta.models == before.meta.models
    assert graph.get_state(thread_config(task_id)).values["model_ids"] == before_pins


def test_human_command_reconstructs_once_then_is_idempotent(tmp_path: Path) -> None:
    root, task_id = _active_task(tmp_path)
    handoffs = []
    request = ProviderRecoveryRequest("codex", {"swe": "offered"})

    first = recover_active_item_provider_command(
        task_id,
        request,
        actor="human",
        root=root,
        inventory=_inventory("offered"),
        kickoff=handoffs.append,
    )
    second = recover_active_item_provider_command(
        task_id,
        request,
        actor="human",
        root=root,
        inventory=_inventory("offered"),
        kickoff=handoffs.append,
    )

    assert first.ok
    assert first.disposition == "fresh_role_turn"
    assert len(handoffs) == 1
    assert handoffs[0].kind == "resume_inflight"
    assert second.ok and second.idempotent
    assert len(handoffs) == 1


def test_recovery_updates_active_epic_in_integration_worktree_when_trunk_has_backlog_copy(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_028", title="Epic", tier="epic", status="backlog")
    worktree = ensure_integration_worktree(
        "epic", "epic_028", branch="epic/epic_028", base_ref="main", trunk=root
    ).path
    move_doc("epic_028", "active", root=worktree)
    assert read_doc("epic_028", root=root).meta.status == "backlog"

    handoffs = []
    request = ProviderRecoveryRequest(
        "codex", {"epic_manager": "offered", "epic_architect": "offered"}
    )
    result = recover_active_item_provider_command(
        "epic_028", request, actor="human", root=root,
        inventory=_inventory("offered"), kickoff=handoffs.append,
    )

    assert result.ok and result.disposition == "fresh_role_turn"
    assert len(handoffs) == 1
    assert read_doc("epic_028", root=root).meta.status == "backlog"
    live = read_doc_in_worktree("epic_028", worktree)
    assert live.meta.status == "active"
    assert live.meta.models == {"epic_manager": "offered", "epic_architect": "offered"}


def test_command_requires_human_authorization(tmp_path: Path) -> None:
    root, task_id = _active_task(tmp_path)

    result = recover_active_item_provider_command(
        task_id,
        ProviderRecoveryRequest("codex", {"swe": "offered"}),
        root=root,
        inventory=_inventory("offered"),
    )

    assert not result.ok
    assert result.error_code == "unauthorized"


_TIER_ROLES = {
    "epic": ("epic_manager", "epic_architect"),
    "feature": ("feature_lead", "feature_architect"),
    "task": ("swe",),
}


def _hierarchy(tmp_path: Path, target_tier: str) -> tuple[Path, str]:
    root = make_repo(tmp_path, git=False, models=True)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    return root, {"epic": "epic_001", "feature": "feat_001", "task": "task_001"}[target_tier]


def _graph_for(work_id: str, tier: str, root: Path, parent: str | None = None):
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph
        return ensure_epic_graph(work_id, root=root), thread_config(work_id)
    if tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph
        return ensure_feature_graph(work_id, root=root), thread_config(work_id)
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph
    return ensure_task_graph(work_id, root=root, feature_id=parent), thread_config(work_id)


def _seed_state(work_id: str, tier: str, root: Path, *, parent: str | None, model: str) -> None:
    graph, config = _graph_for(work_id, tier, root, parent)
    roles = _TIER_ROLES[tier]
    graph.update_state(config, {
        f"{tier}_id": work_id,
        **({"feature_id": parent} if tier == "task" else {}),
        "messages": [
            {"role": "human", "content": f"preserved {tier} plan"},
            {"role": "event", "name": "Progress", "content": "preserved progress"},
        ],
        "last_queue_offset": 17,
        "provider_ids": {role: "codex" for role in roles},
        "provider_sources": {role: "document" for role in roles},
        "model_ids": {role: model for role in roles},
        "model_sources": {role: "document-role" for role in roles},
        "reasoning_ids": {role: "thorough" for role in roles},
        "reasoning_sources": {role: "document-role" for role in roles},
        "flex_modes": {role: True for role in roles},
        "model_id": None,
    })


def _set_document_selection(work_id: str, root: Path, roles: tuple[str, ...], model: str) -> None:
    doc = read_doc(work_id, root=root)
    doc.meta = replace(
        doc.meta,
        provider="codex",
        models={role: model for role in roles},
        reasoning={role: "thorough" for role in roles},
        flex_mode=True,
    )
    write_doc(doc, root=root)


@pytest.mark.parametrize("tier", ("epic", "feature", "task"))
def test_cross_tier_validation_checks_every_role_before_any_mutation(tmp_path: Path, tier: str) -> None:
    root, work_id = _hierarchy(tmp_path, tier)
    target = read_doc(work_id, root=root)
    roles = _TIER_ROLES[tier]
    _seed_state(work_id, tier, root, parent=target.meta.parent, model="old-model")
    graph, config = _graph_for(work_id, tier, root, target.meta.parent)
    before = graph.get_state(config).values
    result = recover_active_item_provider(
        work_id,
        ProviderRecoveryRequest(
            "codex",
            {
                role: ("missing" if index == len(roles) - 1 else "recovered")
                for index, role in enumerate(roles)
            },
            reasoning={role: "thorough" for role in roles},
            flex_mode=True,
        ),
        root=root,
        inventory=_inventory("recovered", reasoning=True, flex=True),
    )

    assert result.disposition == "validation_failed"
    assert [check.role for check in result.checks] == list(roles)
    assert read_doc(work_id, root=root).meta.models is None
    assert graph.get_state(config).values == before


@pytest.mark.parametrize("tier", ("epic", "feature", "task"))
def test_cross_tier_recovery_preserves_context_children_and_dirty_worktree(
    tmp_path: Path, tier: str
) -> None:
    """A changed selection reconstructs just the target's provider turn."""

    root, work_id = _hierarchy(tmp_path, tier)
    target = read_doc(work_id, root=root)
    _seed_state(work_id, tier, root, parent=target.meta.parent, model="old-model")
    before_body = target.body
    child_before = {
        child_id: read_doc(child_id, root=root).meta.models
        for child_id in ("feat_001", "task_001")
        if child_id != work_id
    }
    dirty_worktree = root / "preserved-task-worktree"
    dirty_worktree.mkdir()
    dirty_file = dirty_worktree / "uncommitted.txt"
    dirty_file.write_text("do not discard\n", encoding="utf-8")
    handoffs = []
    roles = _TIER_ROLES[tier]
    request = ProviderRecoveryRequest(
        "codex", {role: "recovered" for role in roles},
        reasoning={role: "thorough" for role in roles}, flex_mode=True,
    )

    first = recover_active_item_provider_command(
        work_id, request, actor="human", root=root,
        inventory=_inventory("recovered", reasoning=True, flex=True), kickoff=handoffs.append,
    )
    second = recover_active_item_provider_command(
        work_id, request, actor="human", root=root,
        inventory=_inventory("recovered", reasoning=True, flex=True), kickoff=handoffs.append,
    )

    assert first.ok and first.disposition == "fresh_role_turn"
    assert second.ok and second.idempotent
    assert len(handoffs) == 1
    assert dirty_file.read_text(encoding="utf-8") == "do not discard\n"
    after = read_doc(work_id, root=root)
    assert after.body == before_body
    assert after.meta.models == {role: "recovered" for role in roles}
    assert after.meta.reasoning == {role: "thorough" for role in roles}
    assert after.meta.flex_mode is True
    assert {
        child_id: read_doc(child_id, root=root).meta.models
        for child_id in child_before
    } == child_before
    graph, config = _graph_for(work_id, tier, root, after.meta.parent)
    state = graph.get_state(config).values
    assert state["last_queue_offset"] == 17
    assert any(message.get("content") == f"preserved {tier} plan" for message in state["messages"])
    assert any(message.get("content") == "preserved progress" for message in state["messages"])
    assert state["messages"][-1]["name"] == "ProviderRecoveryRequested"
    for role in roles:
        assert state["provider_ids"][role] == "codex"
        assert state["model_ids"][role] == "recovered"
        assert state["reasoning_ids"][role] == "thorough"
        assert state["flex_modes"][role] is True


@pytest.mark.parametrize("tier", ("epic", "feature", "task"))
def test_cross_tier_compatible_recovery_resumes_without_reconstructing_turn(
    tmp_path: Path, tier: str
) -> None:
    root, work_id = _hierarchy(tmp_path, tier)
    target = read_doc(work_id, root=root)
    roles = _TIER_ROLES[tier]
    _set_document_selection(work_id, root, roles, "recovered")
    _seed_state(work_id, tier, root, parent=target.meta.parent, model="recovered")
    graph, config = _graph_for(work_id, tier, root, target.meta.parent)
    before_messages = list(graph.get_state(config).values["messages"])
    handoffs = []
    result = recover_active_item_provider_command(
        work_id,
        ProviderRecoveryRequest(
            "codex", {role: "recovered" for role in roles},
            reasoning={role: "thorough" for role in roles}, flex_mode=True,
        ),
        actor="human", root=root,
        inventory=_inventory("recovered", reasoning=True, flex=True), kickoff=handoffs.append,
    )

    assert result.ok and result.disposition == "resume_compatible"
    assert len(handoffs) == 1
    assert graph.get_state(config).values["messages"] == before_messages


def teardown_function() -> None:
    clear_task_graph_sessions()
