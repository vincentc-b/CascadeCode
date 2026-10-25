"""Parse and render work markdown. Heading quality is not judged here."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from cascade.agent.errors import ProviderConfigError
from cascade.agent.providers import parse_provider_id
from cascade.board.errors import SchemaError
from cascade.board.paths import parse_work_id
from cascade.board.work_ids import tier_of_work_id
from cascade.board.types import (
    CancellationFeedback,
    WorkDoc,
    WorkMeta,
    WorkStatus,
    WorkTier,
)

_REQUIRED_KEYS = (
    "id",
    "title",
    "tier",
    "status",
    "parent",
    "children",
    "depends_on",
    "owners",
    "skills",
    "parent_rev",
    "created",
    "updated",
)
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def parse_doc(path: Path) -> WorkDoc:
    """Read YAML frontmatter and the markdown body. Raises SchemaError."""

    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SchemaError(f"cannot read {file_path}: not valid utf-8") from exc
    except OSError as exc:
        raise SchemaError(f"cannot read {file_path}: {exc}") from exc
    return parse_text(text, file_path)


def parse_text(text: str, path: Path) -> WorkDoc:
    """Parse markdown text as if it lived at `path`."""

    frontmatter, body = _split_frontmatter(text)
    try:
        loaded = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        raise SchemaError(f"invalid frontmatter in {Path(path).name}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SchemaError(f"frontmatter in {Path(path).name} must be a mapping")
    meta = _meta_from_mapping(loaded, Path(path))
    return WorkDoc(meta=meta, body=body, sha=None)


def render_doc(doc: WorkDoc) -> str:
    """Serialize a work doc. The path is not written into frontmatter."""

    meta = doc.meta
    payload = {
        "id": meta.id,
        "title": meta.title,
        "tier": meta.tier,
        "status": meta.status,
        "parent": meta.parent,
        "children": list(meta.children),
        "depends_on": list(meta.depends_on),
        "owners": list(meta.owners),
        "skills": [Path(skill).as_posix() for skill in meta.skills],
        "parent_rev": meta.parent_rev,
        "created": meta.created.isoformat(),
        "updated": meta.updated.isoformat(),
    }
    if meta.model is not None:
        payload["model"] = meta.model
    if meta.provider is not None:
        payload["provider"] = meta.provider
    if meta.models:
        payload["models"] = dict(meta.models)
    if meta.reasoning:
        payload["reasoning"] = dict(meta.reasoning)
    if meta.integration_branch is not None:
        payload["integration_branch"] = meta.integration_branch
    if meta.integration_worktree is not None:
        payload["integration_worktree"] = meta.integration_worktree
    if meta.cites:
        payload["cites"] = list(meta.cites)
    if meta.approved_at is not None:
        payload["approved_at"] = meta.approved_at.isoformat()
    if meta.plan_approved_at is not None:
        payload["plan_approved_at"] = meta.plan_approved_at.isoformat()
    if meta.cancellation_reason is not None:
        payload["cancellation_reason"] = meta.cancellation_reason
    if meta.cancelled_at is not None:
        payload["cancelled_at"] = meta.cancelled_at.isoformat()
    if meta.cancellation_step is not None:
        payload["cancellation_step"] = meta.cancellation_step
    if meta.cancellation_error is not None:
        payload["cancellation_error"] = meta.cancellation_error
    if meta.cancellation_feedback:
        payload["cancellation_feedback"] = [
            {
                "child_id": item.child_id,
                "child_tier": item.child_tier,
                "parent_id": item.parent_id,
                "reason": item.reason,
                "cancelled_at": item.cancelled_at.isoformat(),
                "available_dispositions": list(item.available_dispositions),
                "disposition": item.disposition,
                "resolved_at": (
                    item.resolved_at.isoformat() if item.resolved_at is not None else None
                ),
            }
            for item in meta.cancellation_feedback
        ]
    frontmatter = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=4096)
    body = doc.body
    if body and not body.endswith("\n"):
        body += "\n"
    return f"---\n{frontmatter}---\n{body}"


def _split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise SchemaError("missing frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            return frontmatter, body
    raise SchemaError("unterminated frontmatter")


def _meta_from_mapping(loaded: dict[str, object], path: Path) -> WorkMeta:
    missing = [key for key in _REQUIRED_KEYS if key not in loaded]
    if missing:
        raise SchemaError(f"missing frontmatter field(s): {', '.join(missing)}")

    work_id = loaded["id"]
    if not isinstance(work_id, str):
        raise SchemaError("id must be a string")
    tier_from_id = tier_of_work_id(work_id)

    title = loaded["title"]
    if not isinstance(title, str) or not title.strip() or "\n" in title:
        raise SchemaError("title must be a single-line string")

    tier = _require_tier(loaded["tier"])
    if tier != tier_from_id:
        raise SchemaError(f"id {work_id} does not match tier {tier}")
    status = _require_status(loaded["status"])

    parent = loaded["parent"]
    if parent is not None and not isinstance(parent, str):
        raise SchemaError("parent must be a work id or null")
    if isinstance(parent, str) and not parent:
        raise SchemaError("parent must be a work id or null")

    stem = path.stem
    if not (stem == work_id or stem.startswith(work_id + "_")):
        raise SchemaError(f"filename {path.name} does not match id {work_id}")

    return WorkMeta(
        id=work_id,
        title=title,
        tier=tier,
        status=status,
        parent=parent,
        children=_str_list(loaded["children"], "children"),
        depends_on=_str_list(loaded["depends_on"], "depends_on"),
        owners=_str_list(loaded["owners"], "owners"),
        skills=[Path(item) for item in _str_list(loaded["skills"], "skills")],
        parent_rev=_parent_rev(loaded["parent_rev"]),
        created=_as_date(loaded["created"], "created"),
        updated=_as_date(loaded["updated"], "updated"),
        path=path.resolve(),
        model=_optional_model(loaded),
        provider=_optional_provider(loaded),
        models=_optional_models(loaded),
        reasoning=_optional_models(loaded, field="reasoning"),
        integration_branch=_optional_integration_str(loaded, "integration_branch"),
        integration_worktree=_optional_integration_str(loaded, "integration_worktree"),
        cites=_optional_cites(loaded),
        approved_at=_optional_datetime(loaded, "approved_at"),
        plan_approved_at=_optional_datetime(loaded, "plan_approved_at"),
        cancellation_reason=_optional_nonblank_str(loaded, "cancellation_reason"),
        cancelled_at=_optional_datetime(loaded, "cancelled_at"),
        cancellation_step=_optional_nonblank_str(loaded, "cancellation_step"),
        cancellation_error=_optional_nonblank_str(loaded, "cancellation_error"),
        cancellation_feedback=_cancellation_feedback(loaded),
    )



_CANCELLATION_DISPOSITIONS = [
    "continue_reduced_scope", "replace_replan", "cancel_parent"
]


def _cancellation_feedback(loaded: dict[str, object]) -> list[CancellationFeedback]:
    raw = loaded.get("cancellation_feedback", [])
    if not isinstance(raw, list):
        raise SchemaError("cancellation_feedback must be a list")
    feedback: list[CancellationFeedback] = []
    for item in raw:
        if not isinstance(item, dict):
            raise SchemaError("cancellation_feedback entries must be mappings")
        child_id = item.get("child_id")
        parent_id = item.get("parent_id")
        reason = item.get("reason")
        child_tier = item.get("child_tier")
        dispositions = item.get("available_dispositions")
        disposition = item.get("disposition")
        if not isinstance(child_id, str) or not child_id:
            raise SchemaError("cancellation_feedback child_id must be non-blank")
        if not isinstance(parent_id, str) or not parent_id:
            raise SchemaError("cancellation_feedback parent_id must be non-blank")
        if child_tier not in ("feature", "task"):
            raise SchemaError("cancellation_feedback child_tier must be feature or task")
        if not isinstance(reason, str) or not reason.strip():
            raise SchemaError("cancellation_feedback reason must be non-blank")
        if dispositions != _CANCELLATION_DISPOSITIONS:
            raise SchemaError("cancellation_feedback has invalid available_dispositions")
        if disposition is not None and disposition not in _CANCELLATION_DISPOSITIONS:
            raise SchemaError("cancellation_feedback has invalid disposition")
        cancelled_at = _feedback_datetime(item, "cancelled_at", required=True)
        resolved_at = _feedback_datetime(item, "resolved_at", required=False)
        if (disposition is None) != (resolved_at is None):
            raise SchemaError(
                "cancellation_feedback disposition and resolved_at must be set together"
            )
        assert cancelled_at is not None
        feedback.append(CancellationFeedback(
            child_id=child_id,
            child_tier=child_tier,
            parent_id=parent_id,
            reason=reason.strip(),
            cancelled_at=cancelled_at,
            available_dispositions=list(dispositions),
            disposition=disposition,
            resolved_at=resolved_at,
        ))
    return feedback


def _feedback_datetime(
    item: dict[object, object], field: str, *, required: bool
) -> datetime | None:
    value = item.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(
            f"cancellation_feedback {field} must be an ISO-8601 datetime string"
        )
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise SchemaError(f"invalid cancellation_feedback {field}") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _require_tier(value: object) -> WorkTier:
    if value == "epic" or value == "feature" or value == "task":
        return value
    raise SchemaError(f"invalid tier: {value!r}")


def _require_status(value: object) -> WorkStatus:
    if (
        value == "backlog"
        or value == "ready_to_plan"
        or value == "active"
        or value == "blocked"
        or value == "completed"
        or value == "cancelling"
        or value == "cancelled"
    ):
        return value
    raise SchemaError(f"invalid status: {value!r}")


def _str_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaError(f"{field} must be a list of strings")
    return list(value)


def _optional_datetime(loaded: dict[str, object], field: str) -> datetime | None:
    if field not in loaded:
        return None
    value = loaded[field]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{field} must be an ISO-8601 datetime string")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SchemaError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _optional_cites(loaded: dict[str, object]) -> list[str]:
    if "cites" not in loaded:
        return []
    return _str_list(loaded["cites"], "cites")


def _optional_nonblank_str(loaded: dict[str, object], field: str) -> str | None:
    if field not in loaded or loaded[field] is None:
        return None
    value = loaded[field]
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{field} must be a non-blank string")
    return value.strip()


def _optional_integration_str(loaded: dict[str, object], field: str) -> str | None:
    if field not in loaded:
        return None
    value = loaded[field]
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{field} must be a non-blank string")
    return value.strip()


def _optional_model(loaded: dict[str, object]) -> str | None:
    if "model" not in loaded:
        return None
    value = loaded["model"]
    if not isinstance(value, str) or not value.strip():
        raise SchemaError("model must be a non-blank string")
    return value.strip()


def _optional_provider(loaded: dict[str, object]) -> str | None:
    if "provider" not in loaded:
        return None
    value = loaded["provider"]
    if not isinstance(value, str) or not value.strip():
        raise SchemaError("provider must be a non-blank string")
    try:
        return parse_provider_id(value)
    except ProviderConfigError:
        raise


def _optional_models(
    loaded: dict[str, object],
    *,
    field: str = "models",
) -> dict[str, str] | None:
    if field not in loaded:
        return None
    value = loaded[field]
    if not isinstance(value, dict):
        raise SchemaError(f"{field} must be a mapping")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise SchemaError(f"{field} must be a mapping with string keys")
        if not isinstance(item, str) or not item.strip():
            raise SchemaError(f"{field}.{key} must be a non-blank string")
        result[key] = item.strip()
    if not result:
        return None
    return result


def _parent_rev(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and _SHA_RE.fullmatch(value):
        return value.lower()
    raise SchemaError("parent_rev must be a 40-character hex SHA or null")


def _as_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise SchemaError(f"invalid {field}") from exc
    raise SchemaError(f"invalid {field}")
