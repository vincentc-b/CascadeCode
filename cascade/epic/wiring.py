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
    import cascade.epic.decisions as decisions_mod
    import cascade.epic.docs_tool as docs_tool_mod
    import cascade.epic.mint as mint_mod
    import cascade.epic.stubs as stubs_mod

    from cascade.epic.registry import epic_tools

    expected = (
        "mint_feature",
        "list_children",
        "record_decision",
        "read_doc",
        "write_doc",
        "reply_comment",
        "read_comment",
        "resolve_amendment",
    )
    if all(name in epic_tools() for name in expected):
        return
    importlib.reload(mint_mod)
    importlib.reload(decisions_mod)
    importlib.reload(docs_tool_mod)
    importlib.reload(stubs_mod)
    importlib.reload(amendments_mod)


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
