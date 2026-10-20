"""War Room chat → feature graph wiring and lazy tool loading."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.feature.graph import ingest_human, seed_feature_role_models
from cascade.watchdog.boot_model import toast_model_config_failure
from cascade.watchdog.config import ConfigError
from cascade.agent.errors import ProviderConfigError
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend


def load_feature_tools() -> None:
    """Import tool modules so they register. Idempotent."""

    import cascade.feature.amendments as amendments_mod
    import cascade.feature.comments_tool as comments_tool_mod
    import cascade.feature.decisions as decisions_mod
    import cascade.feature.docs_tool as docs_tool_mod
    import cascade.feature.mint as mint_mod

    from cascade.feature.registry import feature_tools, register_feature_tool

    expected = (
        "mint_task",
        "list_children",
        "record_decision",
        "read_doc",
        "write_doc",
        "reply_comment",
        "propose_epic_amendment",
        "ack_amendment",
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
        doc = read_doc(graph_id, root=repo)
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
        seed_feature_role_models(
            graph_id,
            lead=lead,
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
