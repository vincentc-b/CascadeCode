"""War Room chat → feature graph wiring and lazy tool loading."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.feature.graph import ingest_human, seed_feature_role_models
from cascade.watchdog.boot_model import toast_model_config_failure
from cascade.watchdog.config import ConfigError
from cascade.agent.errors import ProviderConfigError
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend


def load_feature_tools() -> None:
    """Import tool modules so they register. Idempotent."""

    import cascade.feature.amendments as amendments_mod
    import cascade.feature.audit_recovery as audit_recovery_mod
    import cascade.feature.branch_recovery as branch_recovery_mod
    import cascade.feature.comments_tool as comments_tool_mod
    import cascade.feature.decisions as decisions_mod
    import cascade.feature.docs_tool as docs_tool_mod
    import cascade.feature.mint as mint_mod
    import cascade.feature.recovery as recovery_mod
    import cascade.feature.review_recovery as review_recovery_mod
    import cascade.planning_dependency_tools as dependency_tools_mod
    from cascade.review import reply_feature_review

    from cascade.feature.registry import feature_tools, register_feature_tool
    from cascade.team_supervision import message_team, supervise_child
    register_feature_tool("message_team", message_team)
    register_feature_tool("supervise_child", supervise_child)
    from cascade.watchdog.audit_investigation import report_audit_investigation
    register_feature_tool("report_audit_investigation", report_audit_investigation)

    expected = (
        "mint_task", "list_children", "record_decision", "read_doc", "write_doc",
        "reply_comment", "propose_epic_amendment", "ack_amendment",
        "reply_merge_request_comment", "revise_task", "retry_task", "recovery_status",
        "recover_task",
        "refresh_dependency_status",
        "retry_integration_branch_update",
        "publish_review_resolution",
        "resume_planning_owner",
        "restore_child_dispatch",
        "retry_owned_publication",
        "publish_integration_review",
        "reconcile_completion_rollup",
    )
    if all(name in feature_tools() for name in expected):
        return
    register_feature_tool("mint_task", mint_mod.mint_task)
    register_feature_tool("record_decision", decisions_mod.record_decision)
    register_feature_tool("read_doc", docs_tool_mod.read_doc)
    register_feature_tool("write_doc", docs_tool_mod.write_doc)
    register_feature_tool("list_children", docs_tool_mod.list_children)
    register_feature_tool("reply_comment", comments_tool_mod.reply_comment)
    register_feature_tool("propose_epic_amendment", amendments_mod.propose_epic_amendment)
    register_feature_tool("ack_amendment", amendments_mod.ack_amendment)
    register_feature_tool("reply_merge_request_comment", reply_feature_review)
    register_feature_tool("revise_task", recovery_mod.revise_task)
    register_feature_tool("retry_task", recovery_mod.retry_task)
    register_feature_tool("recovery_status", recovery_mod.recovery_status)
    register_feature_tool("recover_task", recovery_mod.recover_task)
    register_feature_tool(
        "refresh_dependency_status", dependency_tools_mod.refresh_feature_dependencies
    )
    register_feature_tool(
        "retry_integration_branch_update",
        branch_recovery_mod.retry_integration_branch_update,
    )
    register_feature_tool(
        "publish_review_resolution",
        review_recovery_mod.publish_review_resolution,
    )
    register_feature_tool(
        "resume_planning_owner", audit_recovery_mod.resume_planning_owner
    )
    register_feature_tool(
        "restore_child_dispatch", audit_recovery_mod.restore_child_dispatch
    )
    register_feature_tool(
        "retry_owned_publication", audit_recovery_mod.retry_owned_publication
    )
    register_feature_tool(
        "publish_integration_review", audit_recovery_mod.publish_integration_review
    )
    register_feature_tool(
        "reconcile_completion_rollup", audit_recovery_mod.reconcile_completion_rollup
    )


def accept_human_chat(
    graph_id: str,
    message: dict,
    *,
    root: Path,
    model_id: str | None = None,
) -> None:
    """If graph_id is a feature work doc, ingest the human message into the feature graph."""

    repo = Path(root).resolve()
    try:
        from cascade.workspace.doc_root import read_doc_resolved

        doc = read_doc_resolved(graph_id, root=repo)
    except NotFound:
        return
    if doc.meta.tier != "feature":
        return

    load_feature_tools()
    explicit_model = model_id is not None and str(model_id).strip()
    if not explicit_model:
        try:
            lead = resolve_backend("feature_lead", doc.meta, root=repo)
            architect = resolve_backend("feature_architect", doc.meta, root=repo)
        except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
            toast_model_config_failure(graph_id, str(exc), root=repo)
            raise
        seed_feature_role_models(graph_id, lead=lead, architect=architect, root=repo)
        model_id = None
    ingest_human(
        graph_id,
        {"role": "human", "content": message["body"], "id": message.get("id"), "ts": message.get("ts")},
        root=repo,
        model_id=model_id,
    )
