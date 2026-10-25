"""Lossless model for editing an existing backlog epic brief."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from cascade.agent.discovery.inventory import ProviderInventoryResult, get_provider_inventory
from cascade.agent.providers import parse_provider_id
from cascade.board.parse import render_doc
from cascade.board.types import WorkDoc
from cascade.brief_stack import (
    BRIEF_STACK_ROLES, normalize_reasoning_overrides, parse_brief_models,
    validate_models_against_inventory,
)
from cascade.briefs import _clean
from cascade.watchdog.config import read_providers_config


@dataclass(frozen=True)
class BriefEditSource:
    work_id: str
    path: Path
    revision: str | None


@dataclass(frozen=True)
class BriefEditRequest:
    title: str
    intent: str
    success_criteria: str
    constraints: str
    provider: str
    models: dict[str, str]
    reasoning: dict[str, str]
    cleared_reasoning: frozenset[str]
    source: BriefEditSource
    original: WorkDoc
    additional_markdown: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def source_revision(self) -> str | None:
        return self.source.revision


def load_brief_edit(doc: WorkDoc) -> dict[str, object]:
    models = dict(doc.meta.models or {})
    return {
        "title": doc.meta.title, "intent": _section_value(doc.body, "Intent"),
        "success_criteria": _section_value(doc.body, "Success criteria"),
        "constraints": _section_value(doc.body, "Cross-module constraints"),
        "provider": doc.meta.provider,
        "models": {role: models.get(role, "") for role in BRIEF_STACK_ROLES},
        "reasoning": dict(doc.meta.reasoning or {}),
        "additional_markdown": _additional_markdown(doc.body, doc.meta.title),
        "source": BriefEditSource(doc.meta.id, doc.meta.path, doc.sha),
    }


def validate_brief_edit(
    raw: dict[str, object],
    target: WorkDoc,
    *,
    root: Path,
    inventory: ProviderInventoryResult | None = None,
) -> BriefEditRequest:
    if target.meta.tier != "epic" or target.meta.status != "backlog":
        raise ValueError("only backlog epic briefs can be edited")
    config = read_providers_config(root)
    provider = parse_provider_id(_clean(str(raw.get("provider") or ""), "provider"))
    models = parse_brief_models(raw, table=config.tables[provider])
    saved = dict(target.meta.models or {})
    warnings: list[str] = []
    try:
        item = validate_models_against_inventory(
            provider, models, inventory or get_provider_inventory()
        )
    except ValueError as exc:
        if provider != target.meta.provider or any(
            models.get(role) != saved.get(role) for role in BRIEF_STACK_ROLES
        ):
            raise
        item = None
        warnings.append(str(exc))
    reasoning_input, cleared = _parse_reasoning(raw)
    reasoning = (
        dict(reasoning_input)
        if item is None
        else normalize_reasoning_overrides(
            models, reasoning_input, provider_item=item
        )
    )
    reasoning = {role: value for role, value in reasoning.items() if role not in cleared}
    additional = raw.get("additional_markdown")
    if additional is not None and not isinstance(additional, str):
        raise ValueError("additional markdown must be text")
    return BriefEditRequest(
        title=_clean(str(raw.get("title") or ""), "title"),
        intent=_clean(str(raw.get("intent") or ""), "intent"),
        success_criteria=_clean(str(raw.get("success_criteria") or ""), "success criteria"),
        constraints=str(raw.get("constraints") or "").strip(),
        provider=provider,
        models=models,
        reasoning=reasoning,
        cleared_reasoning=frozenset(cleared),
        source=BriefEditSource(target.meta.id, target.meta.path, target.sha),
        original=target,
        additional_markdown=additional,
        warnings=tuple(warnings),
    )


def render_brief_edit(edit: BriefEditRequest) -> WorkDoc:
    body = edit.original.body
    if edit.title != edit.original.meta.title:
        old_heading = f"# {edit.original.meta.title}"
        if body.startswith(old_heading + "\n"):
            body = f"# {edit.title}" + body[len(old_heading):]
    body = _replace_section(body, "Intent", edit.intent)
    body = _replace_section(body, "Success criteria", edit.success_criteria)
    body = _replace_section(body, "Cross-module constraints", edit.constraints)
    original_additional = _additional_markdown(edit.original.body, edit.original.meta.title)
    requested_additional = (
        original_additional
        if edit.additional_markdown is None
        else edit.additional_markdown.strip()
    )
    if requested_additional != original_additional.strip():
        if original_additional:
            body = body.replace(original_additional, "", 1).rstrip()
        if requested_additional:
            body = body + "\n\n" + requested_additional + "\n"
    meta = replace(
        edit.original.meta,
        title=edit.title,
        provider=edit.provider,
        models=dict(edit.models),
        reasoning=dict(edit.reasoning) or None,
        updated=edit.original.meta.updated,
    )
    return WorkDoc(meta=meta, body=body, sha=edit.original.sha)


def render_brief_edit_text(edit: BriefEditRequest) -> str:
    return render_doc(render_brief_edit(edit))


def brief_edit_unchanged(edit: BriefEditRequest) -> bool:
    before, after = edit.original, render_brief_edit(edit)
    return (
        before.meta.title.strip() == after.meta.title.strip()
        and before.meta.provider == after.meta.provider
        and dict(before.meta.models or {}) == dict(after.meta.models or {})
        and dict(before.meta.reasoning or {}) == dict(after.meta.reasoning or {})
        and before.body == after.body
    )


def _parse_reasoning(raw: dict[str, object]) -> tuple[dict[str, str], set[str]]:
    value = raw.get("reasoning")
    if value is None:
        return {}, set()
    if not isinstance(value, dict):
        raise ValueError("reasoning must be a mapping")
    result: dict[str, str] = {}
    cleared: set[str] = set()
    for role, level in value.items():
        if role not in BRIEF_STACK_ROLES:
            raise ValueError(f"unsupported reasoning role: {role!r}")
        if level is None or (isinstance(level, str) and not level.strip()):
            cleared.add(role)
        else:
            result[role] = str(level).strip()
    return result, cleared


def _section_value(body: str, heading: str) -> str:
    match = re.search(
        r"(?ms)^##{1,3} +" + re.escape(heading) + r" *\n(.*?)(?=^##{1,3} +|\Z)",
        body,
    )
    return match.group(1).strip() if match else ""


def _additional_markdown(body: str, title: str) -> str:
    """Return human-authored sections outside the three structured fields."""
    value = body
    if value.startswith(f"# {title}\n"):
        value = value[len(f"# {title}\n"):]
    headings = {"intent", "success criteria", "cross-module constraints"}
    matches = list(re.finditer(r"(?m)^#{2,3} +(.+?) *$", value))
    spans: list[tuple[int, int]] = []
    for index, match in enumerate(matches):
        if match.group(1).strip().lower() not in headings:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        spans.append((match.start(), end))
    for start, end in reversed(spans):
        value = value[:start] + value[end:]
    return value.strip()


def _replace_section(body: str, heading: str, value: str) -> str:
    pattern = re.compile(
        r"(?ms)(^##{1,3} +" + re.escape(heading) + r" *\n)(.*?)(?=^##{1,3} +|\Z)"
    )
    match = pattern.search(body)
    if not match:
        if not value.strip():
            return body
        return body.rstrip("\n") + f"\n\n## {heading}\n\n{value.strip()}\n"
    if match.group(2).strip() == value.strip():
        return body
    return body[:match.start(2)] + value.strip() + "\n\n" + body[match.end(2):].lstrip("\n")
