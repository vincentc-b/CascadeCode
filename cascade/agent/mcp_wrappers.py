"""MCP stdio server config and guarded Cascade tool dispatch for planning turns."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from cursor_sdk import CustomTool, CustomToolContext

from cascade.agent.planning_sandbox import PlanningSandbox, PlanningTier
from cascade.agent.types import ToolEffect
from cascade.board.serde import work_doc_from_dict
from cascade.watchdog.dispatch import dispatch_feature, dispatch_task
from cascade.watchdog.types import DispatchResult

MCP_SERVER_NAME = "cascade"

PlanningToolTier = Literal["epic", "feature", "boss"]


@dataclass
class ToolEffectCollector:
    effects: list[ToolEffect] = field(default_factory=list)

    def record(self, tool: str, result: object) -> None:
        self.effects.append(ToolEffect(tool=tool, summary=_summarize_result(result)))


def _planning_tool_names(sandbox: PlanningSandbox) -> list[str]:
    if sandbox.tier == "epic":
        from cascade.epic.wiring import load_epic_tools

        load_epic_tools()
        return sorted(_epic_tool_names())
    if sandbox.tier == "feature":
        from cascade.feature.wiring import load_feature_tools

        load_feature_tools()
        return sorted(_feature_tool_names())
    return sorted(_BOSS_TOOL_NAMES)


def build_planning_custom_tools(
    sandbox: PlanningSandbox,
    collector: ToolEffectCollector,
) -> dict[str, CustomTool]:
    """Return SDK ``local.custom_tools`` for Cursor planning turns."""

    tier = sandbox.tier
    tool_names = _planning_tool_names(sandbox)
    schemas = {**_EPIC_TOOL_SCHEMAS, **_FEATURE_TOOL_SCHEMAS, **_BOSS_TOOL_SCHEMAS}
    tools: dict[str, CustomTool] = {}

    for name in tool_names:
        schema = schemas.get(name, {"type": "object", "properties": {}})

        def _execute(
            args: Mapping[str, Any],
            _ctx: CustomToolContext,
            *,
            tool_name: str = name,
        ) -> object:
            return dispatch_planning_tool(
                tier,
                tool_name,
                dict(args),
                scope_id=sandbox.scope_id,
                repo_root=sandbox.repo_root,
                collector=collector,
            )

        tools[name] = CustomTool(
            description=f"Cascade {tier} tool {name}",
            input_schema=schema,
            execute=_execute,
        )
    return tools


def build_planning_mcp_servers(
    sandbox: PlanningSandbox,
    *,
    config_path: Path | None = None,
) -> dict[str, Mapping[str, Any]]:
    """Return SDK ``mcp_servers`` mapping for one planning turn (CLI providers)."""

    tool_names = _planning_tool_names(sandbox)

    cfg_path = config_path or (sandbox.scratch_dir / ".cascade_mcp.json")
    cfg_path.write_text(
        json.dumps(
            {
                "tier": sandbox.tier,
                "scope_id": sandbox.scope_id,
                "repo_root": str(sandbox.repo_root),
                "tool_names": tool_names,
            }
        ),
        encoding="utf-8",
    )

    return {
        MCP_SERVER_NAME: {
            "command": sys.executable,
            "args": ["-m", "cascade.agent.mcp_stdio"],
            "env": {
                "CASCADE_MCP_CONFIG": str(cfg_path),
                "CASCADE_MCP_EFFECTS": str(sandbox.scratch_dir / ".cascade_effects.jsonl"),
            },
            "cwd": str(sandbox.repo_root),
        }
    }


def _normalize_planning_tool_args(
    tier: PlanningToolTier,
    name: str,
    args: dict[str, Any],
    *,
    scope_id: str | None,
    repo: Path,
) -> dict[str, Any]:
    """Coerce MCP/LLM JSON into types graph tools expect."""

    normalized = dict(args)
    if name == "write_doc":
        doc_payload = normalized.get("doc")
        if doc_payload is None and "body" in normalized and "meta" in normalized:
            doc_payload = {
                "meta": normalized.pop("meta"),
                "body": normalized.pop("body"),
                "sha": normalized.pop("sha", None),
            }
        if doc_payload is None:
            raise ValueError("write_doc requires a doc object")
        hint = scope_id if tier == "epic" else (scope_id if tier == "feature" else None)
        normalized["doc"] = work_doc_from_dict(
            doc_payload,
            root=repo,
            work_id_hint=hint if isinstance(hint, str) else None,
        )
    if name == "record_decision" and "text" in normalized and "choice" not in normalized:
        text = str(normalized.pop("text"))
        normalized.setdefault("choice", text)
        normalized.setdefault("rationale", text)
        normalized.setdefault("honors", "")
    return normalized


def dispatch_planning_tool(
    tier: PlanningToolTier,
    name: str,
    args: dict[str, Any],
    *,
    scope_id: str | None,
    repo_root: Path,
    collector: ToolEffectCollector,
) -> object:
    """Invoke a guarded Cascade tool (same entrypoints graphs use)."""

    repo = Path(repo_root).resolve()
    if tier in ("epic", "feature") and name in ("dispatch_feature", "dispatch_task"):
        raise ValueError(f"{name} is not available during {tier} planning turns")
    tool_args = _normalize_planning_tool_args(
        tier, name, dict(args), scope_id=scope_id, repo=repo
    )
    if tier == "epic":
        if not scope_id:
            raise ValueError("epic tier requires scope_id")
        from cascade.epic.wiring import load_epic_tools
        from cascade.epic.graph import invoke_tool

        load_epic_tools()

        result = invoke_tool(scope_id, name, tool_args, root=repo)
    elif tier == "feature":
        if not scope_id:
            raise ValueError("feature tier requires scope_id")
        from cascade.feature.wiring import load_feature_tools
        from cascade.feature.graph import invoke_tool

        load_feature_tools()

        result = invoke_tool(scope_id, name, tool_args, root=repo)
    else:
        result = _invoke_boss_tool(name, tool_args, root=repo)

    collector.record(name, result)
    _append_effect_file(repo, name, result)
    return result


def _invoke_boss_tool(name: str, args: dict[str, Any], *, root: Path) -> object:
    if name == "dispatch_feature":
        work_id = args.get("work_id") or args.get("id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError("dispatch_feature requires work_id")
        return dispatch_feature(work_id, "boss", root=root)
    if name == "dispatch_task":
        work_id = args.get("work_id") or args.get("id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError("dispatch_task requires work_id")
        return dispatch_task(work_id, "boss", root=root)
    if name == "get_boss_view":
        from cascade.boss.view import compute_boss_view

        return compute_boss_view(root=root)
    raise KeyError(name)


def merge_tool_effects_from_file(
    path: Path,
    *,
    base: list[ToolEffect] | None = None,
) -> list[ToolEffect]:
    """Read effects appended by the stdio MCP child process."""

    effects = list(base or [])
    if not path.is_file():
        return effects
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        effects.append(
            ToolEffect(tool=str(payload["tool"]), summary=str(payload.get("summary", "")))
        )
    return effects


def mcp_tool_catalog(tier: PlanningToolTier, tool_names: list[str]) -> list[dict[str, Any]]:
    schemas = {**_EPIC_TOOL_SCHEMAS, **_FEATURE_TOOL_SCHEMAS, **_BOSS_TOOL_SCHEMAS}
    tools: list[dict[str, Any]] = []
    for name in tool_names:
        schema = schemas.get(name, {"type": "object", "properties": {}})
        tools.append(
            {
                "name": name,
                "description": f"Cascade {tier} tool {name}",
                "inputSchema": schema,
            }
        )
    return tools


def _epic_tool_names() -> set[str]:
    from cascade.epic.registry import epic_tools

    return set(epic_tools())


def _feature_tool_names() -> set[str]:
    from cascade.feature.registry import feature_tools

    return set(feature_tools())


_BOSS_TOOL_NAMES = frozenset({"dispatch_feature", "dispatch_task", "get_boss_view"})

_EPIC_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "mint_feature": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "depends_on": {"type": "array", "items": {"type": "string"}},
            "body_stub": {"type": "string"},
        },
        "required": ["title"],
    },
    "list_children": {"type": "object", "properties": {}},
    "record_decision": {
        "type": "object",
        "properties": {
            "section": {"type": "string"},
            "choice": {"type": "string"},
            "rationale": {"type": "string"},
            "honors": {"type": "string"},
            "author": {"type": "string"},
        },
        "required": ["section", "choice", "rationale", "honors"],
    },
    "read_doc": {
        "type": "object",
        "properties": {"work_id": {"type": "string"}},
        "required": ["work_id"],
    },
    "write_doc": {
        "type": "object",
        "properties": {
            "doc": {
                "type": "object",
                "properties": {
                    "meta": {"type": "object"},
                    "body": {"type": "string"},
                    "sha": {"type": "string"},
                },
                "required": ["meta", "body"],
            }
        },
        "required": ["doc"],
    },
    "reply_comment": {
        "type": "object",
        "properties": {
            "comment_id": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["comment_id", "body"],
    },
    "resolve_amendment": {
        "type": "object",
        "properties": {"amendment_id": {"type": "string"}},
        "required": ["amendment_id"],
    },
}

_FEATURE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "mint_task": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "depends_on": {"type": "array", "items": {"type": "string"}},
            "body_stub": {"type": "string"},
        },
        "required": ["title"],
    },
    "list_children": {"type": "object", "properties": {}},
    "record_decision": {
        "type": "object",
        "properties": {
            "section": {"type": "string"},
            "choice": {"type": "string"},
            "rationale": {"type": "string"},
            "honors": {"type": "string"},
            "author": {"type": "string"},
        },
        "required": ["section", "choice", "rationale", "honors"],
    },
    "read_doc": {
        "type": "object",
        "properties": {"work_id": {"type": "string"}},
        "required": ["work_id"],
    },
    "write_doc": {
        "type": "object",
        "properties": {
            "doc": {
                "type": "object",
                "properties": {
                    "meta": {"type": "object"},
                    "body": {"type": "string"},
                    "sha": {"type": "string"},
                },
                "required": ["meta", "body"],
            }
        },
        "required": ["doc"],
    },
    "reply_comment": {
        "type": "object",
        "properties": {
            "comment_id": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["comment_id", "body"],
    },
    "propose_epic_amendment": {"type": "object", "properties": {}},
    "ack_amendment": {"type": "object", "properties": {}},
}

_BOSS_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "dispatch_feature": {
        "type": "object",
        "properties": {"work_id": {"type": "string"}},
        "required": ["work_id"],
    },
    "dispatch_task": {
        "type": "object",
        "properties": {"work_id": {"type": "string"}},
        "required": ["work_id"],
    },
    "get_boss_view": {"type": "object", "properties": {}},
}


def _summarize_result(result: object) -> str:
    if isinstance(result, DispatchResult):
        parts = [f"ok={result.ok}"]
        if result.reason:
            parts.append(f"reason={result.reason}")
        return " ".join(parts)
    text = repr(result)
    if len(text) > 240:
        return text[:237] + "..."
    return text


def _append_effect_file(_repo: Path, tool: str, result: object) -> None:
    import os

    effects_path = os.environ.get("CASCADE_MCP_EFFECTS")
    if not effects_path:
        return
    path = Path(effects_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"tool": tool, "summary": _summarize_result(result)}) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
