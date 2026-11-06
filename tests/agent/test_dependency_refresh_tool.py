"""Planning-tool transports for scope-bound dependency refresh."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

from cascade.agent.mcp_stdio import _handle_message
from cascade.agent.mcp_wrappers import (
    ToolEffectCollector,
    build_planning_custom_tools,
    mcp_tool_catalog,
)
from cascade.agent.planning_sandbox import PlanningSandbox
from cascade.board.store import move_doc
from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
from tests.support import add_doc, make_repo

Tier = Literal["epic", "feature"]
Transport = Literal["custom", "mcp"]


def _board_for_tier(tmp_path: Path, tier: Tier) -> tuple[Path, str, str, str]:
    root = make_repo(tmp_path)
    if tier == "epic":
        dependency_id = "epic_002"
        owner_id = "epic_001"
        unrelated_id = "epic_003"
        add_doc(
            root,
            id=dependency_id,
            title="Private dependency",
            tier="epic",
            status="completed",
        )
        add_doc(root, id=unrelated_id, title="Unrelated private epic", tier="epic")
        add_doc(
            root,
            id=owner_id,
            title="Owner",
            tier="epic",
            status="active",
            depends_on=[dependency_id],
        )
    else:
        add_doc(root, id="epic_001", title="Owner epic", tier="epic", status="active")
        add_doc(root, id="epic_002", title="Other epic", tier="epic", status="active")
        dependency_id = "feat_002"
        owner_id = "feat_001"
        unrelated_id = "feat_003"
        add_doc(
            root,
            id=dependency_id,
            title="Private dependency",
            tier="feature",
            status="completed",
            parent="epic_002",
        )
        add_doc(
            root,
            id=unrelated_id,
            title="Unrelated private feature",
            tier="feature",
            parent="epic_002",
        )
        add_doc(
            root,
            id=owner_id,
            title="Owner",
            tier="feature",
            status="active",
            parent="epic_001",
            depends_on=[dependency_id],
        )
    return root, owner_id, dependency_id, unrelated_id


@pytest.mark.parametrize("tier", ["epic", "feature"])
@pytest.mark.parametrize("transport", ["custom", "mcp"])
def test_dependency_refresh_is_scope_bound_and_fresh_across_planning_transports(
    tmp_path: Path,
    tier: Tier,
    transport: Transport,
) -> None:
    root, owner_id, dependency_id, unrelated_id = _board_for_tier(tmp_path, tier)
    collector = ToolEffectCollector()
    sandbox = PlanningSandbox(
        scratch_dir=tmp_path / "scratch",
        repo_root=root,
        tier=tier,
        scope_id=owner_id,
    )
    tools = build_planning_custom_tools(sandbox, collector)
    assert "refresh_dependency_status" in tools
    assert tools["refresh_dependency_status"].input_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
        if transport == "custom":
            return tools[name].execute(  # type: ignore[no-any-return,arg-type]
                arguments, None
            )
        response = _handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            tier,
            owner_id,
            root,
            list(tools),
            collector,
        )
        assert response is not None
        result = response["result"]
        if result.get("isError"):
            raise PermissionError(result["content"][0]["text"])
        return json.loads(result["content"][0]["text"])

    initial = call("refresh_dependency_status", {})
    assert initial["owner_work_id"] == owner_id
    assert initial["outcome"] == "satisfied"
    assert [row["work_id"] for row in initial["dependencies"]] == [dependency_id]  # type: ignore[index]
    assert unrelated_id not in repr(initial)

    move_doc(dependency_id, "active", root=root)
    refreshed = call("refresh_dependency_status", {})
    assert refreshed["outcome"] == "dependency_unmet"
    assert refreshed["dependencies"][0]["status"] == "active"  # type: ignore[index]
    assert refreshed["snapshot_fingerprint"] != initial["snapshot_fingerprint"]

    stale = merged_board(root)
    move_doc(dependency_id, "completed", root=root)
    with merged_board_snapshot(root, stale):
        request_refreshed = call("refresh_dependency_status", {})
    assert request_refreshed["outcome"] == "satisfied"

    with pytest.raises((PermissionError, TypeError)):
        call("refresh_dependency_status", {"work_id": unrelated_id})
    with pytest.raises(PermissionError, match="^content_access_denied$"):
        call("read_doc", {"work_id": dependency_id})

    catalog = mcp_tool_catalog(tier, list(tools))
    refresh_schema = next(
        item["inputSchema"]
        for item in catalog
        if item["name"] == "refresh_dependency_status"
    )
    assert refresh_schema["additionalProperties"] is False
