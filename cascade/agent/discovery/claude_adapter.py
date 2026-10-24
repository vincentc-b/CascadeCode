"""Anthropic model catalog discovery via the Claude API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping

from cascade.agent.credentials import resolve_credential
from cascade.agent.discovery.availability import require_probe, unavailable_snapshot
from cascade.agent.discovery.normalize import (
    discovered_model,
    normalize_display_name,
    normalize_model_id,
    reasoning_from_codex_record,
    sanitize_provider_error,
    sort_models,
)
from cascade.agent.discovery.types import ProviderDiscoverySnapshot
from cascade.agent.providers import ProviderId

_ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
_ANTHROPIC_VERSION = "2023-06-01"


def _anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "Accept": "application/json",
    }


def _fetch_claude_model_pages(api_key: str) -> list[Mapping[str, Any]]:
    collected: list[Mapping[str, Any]] = []
    after: str | None = None
    for _ in range(32):
        url = _ANTHROPIC_MODELS_URL
        if after:
            url = f"{url}?after={after}"
        request = urllib.request.Request(url, headers=_anthropic_headers(api_key), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        if not isinstance(payload, Mapping):
            raise TypeError("anthropic models payload must be an object")
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, Mapping):
                    collected.append(item)
        if not payload.get("has_more"):
            break
        next_after = payload.get("last_id")
        if not isinstance(next_after, str) or not next_after.strip():
            break
        after = next_after.strip()
    return collected


def _reasoning_from_claude_record(record: Mapping[str, Any]):
    # Anthropic catalog entries may mirror effort metadata when present.
    if "default_reasoning_level" in record or "supported_reasoning_levels" in record:
        return reasoning_from_codex_record(record)
    return None


def discover_claude_models() -> ProviderDiscoverySnapshot:
    provider_id: ProviderId = "claude"
    blocked = require_probe(provider_id)
    if blocked is not None:
        return blocked

    cred = resolve_credential(provider_id)
    if cred is None:
        return unavailable_snapshot(
            provider_id,
            failure="not_authenticated",
            message="claude is not authenticated",
        )

    try:
        records = _fetch_claude_model_pages(cred.token)
    except Exception as exc:
        return unavailable_snapshot(
            provider_id,
            failure="api_error",
            message=sanitize_provider_error(exc),
        )

    models = []
    for record in records:
        model_id = normalize_model_id(record.get("id"))
        if model_id is None:
            continue
        models.append(
            discovered_model(
                model_id=model_id,
                display_name=normalize_display_name(
                    model_id, record.get("display_name")
                ),
                reasoning=_reasoning_from_claude_record(record),
            )
        )

    if not models:
        return unavailable_snapshot(
            provider_id,
            failure="api_error",
            message="empty model catalog",
        )

    return ProviderDiscoverySnapshot(
        provider_id=provider_id,
        available=True,
        models=sort_models(models),
    )
