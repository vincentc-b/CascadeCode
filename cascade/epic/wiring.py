"""War Room chat → epic graph wiring and lazy tool loading."""

from __future__ import annotations

import importlib
from pathlib import Path

from cascade.board.errors import NotFound
from cascade.epic.graph import ingest_human, seed_epic_role_models
from cascade.watchdog.boot_model import toast_model_config_failure
from cascade.watchdog.config import ConfigError
from cascade.agent.errors import ProviderConfigError
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend


def load_epic_tools() -> None:
    """Import tool modules so they register. Idempotent."""

    import cascade.epic.amendments as amendments_mod
    import cascade.epic.branch_recovery as branch_recovery_mod
    import cascade.epic.change_dispositions as change_dispositions_mod
    import cascade.epic.decisions as decisions_mod
    import cascade.epic.docs_tool as docs_tool_mod
    import cascade.epic.impact_decisions as impact_decisions_mod
    import cascade.epic.dependency_manifest_authoring as manifest_mod
    import cascade.epic.dependency_checks as dependency_checks_mod
    import cascade.epic.mint as mint_mod
    import cascade.epic.recovery as recovery_mod
    import cascade.epic.review_recovery as review_recovery_mod
    import cascade.epic.stubs as stubs_mod
    import cascade.planning_dependency_tools as dependency_tools_mod
    from cascade.planning_architecture_tools import publish_epic_architecture_review

    from cascade.epic.registry import epic_tools, register_epic_tool
    from cascade.team_supervision import message_team, supervise_child
    from cascade.architecture_context_tools import (
        read_epic_architecture_amendments,
        read_epic_historical_evidence,
    )
    register_epic_tool("message_team", message_team)
    register_epic_tool("supervise_child", supervise_child)
    register_epic_tool("read_historical_evidence", read_epic_historical_evidence)
    register_epic_tool("read_architecture_amendments", read_epic_architecture_amendments)
    register_epic_tool("publish_architecture_review", publish_epic_architecture_review)
    from cascade.watchdog.audit_investigation import report_audit_investigation
    register_epic_tool("report_audit_investigation", report_audit_investigation)

    expected = (
        "read_dependency_manifest",
        "write_dependency_manifest",
        "run_dependency_check",
        "mint_feature",
        "list_children",
        "record_decision",
        "record_impact_decision",
        "apply_impact_disposition",
        "sign_off_corrective_plan",
        "read_doc",
        "write_doc",
        "reply_comment",
        "read_comment",
        "resolve_amendment",
        "reconcile_stacked_review_gap",
        "resume_owner",
        "restore_feature_dispatch",
        "recover_feature",
        "publish_integration_review",
        "reconcile_completion_rollup",
        "refresh_dependency_status",
        "retry_integration_branch_update",
        "publish_review_resolution",
        "read_historical_evidence",
        "read_architecture_amendments",
        "publish_architecture_review",
    )
    if all(name in epic_tools() for name in expected):
        return
    register_epic_tool("read_dependency_manifest", manifest_mod.read_dependency_manifest)
    register_epic_tool("write_dependency_manifest", manifest_mod.write_dependency_manifest)
    register_epic_tool("run_dependency_check", dependency_checks_mod.run_dependency_check)
    importlib.reload(mint_mod)
    importlib.reload(decisions_mod)
    importlib.reload(impact_decisions_mod)
    importlib.reload(change_dispositions_mod)
    importlib.reload(docs_tool_mod)
    importlib.reload(stubs_mod)
    importlib.reload(amendments_mod)
    importlib.reload(recovery_mod)
    register_epic_tool(
        "refresh_dependency_status", dependency_tools_mod.refresh_epic_dependencies
    )
    importlib.reload(branch_recovery_mod)
    importlib.reload(review_recovery_mod)


def accept_human_chat(
    graph_id: str,
    message: dict,
    *,
    root: Path,
    model_id: str | None = None,
) -> None:
    """If graph_id is an epic work doc, ingest the human message into the epic graph."""

    repo = Path(root).resolve()
    try:
        from cascade.workspace.doc_root import read_doc_resolved

        doc = read_doc_resolved(graph_id, root=repo)
    except NotFound:
        return
    if doc.meta.tier != "epic":
        return

    load_epic_tools()
    explicit_model = model_id is not None and str(model_id).strip()
    if not explicit_model:
        try:
            manager = resolve_backend("epic_manager", doc.meta, root=repo)
            architect = resolve_backend("epic_architect", doc.meta, root=repo)
        except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
            toast_model_config_failure(graph_id, str(exc), root=repo)
            raise
        seed_epic_role_models(
            graph_id,
            manager=manager,
            architect=architect,
            root=repo,
        )
        model_id = None
    ingest_human(
        graph_id,
        {
            "role": "human",
            "content": message["body"],
            "id": message.get("id"),
            "ts": message.get("ts"),
        },
        root=repo,
        model_id=model_id,
    )
