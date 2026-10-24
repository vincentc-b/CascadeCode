"""Cursor cloud model catalog discovery via cursor_sdk."""

from __future__ import annotations

from typing import Any, Sequence

from cascade.agent.credentials import resolve_credential
from cascade.agent.discovery.availability import require_probe, unavailable_snapshot
from cascade.agent.discovery.normalize import (
    discovered_model,
    normalize_display_name,
    normalize_model_id,
    reasoning_from_cursor_parameters,
    sanitize_provider_error,
    sort_models,
)
from cascade.agent.discovery.types import ProviderDiscoverySnapshot
from cascade.agent.providers import ProviderId


def _list_cursor_sdk_models(api_key: str) -> Sequence[Any]:
    from cursor_sdk import Cursor

    return Cursor.models.list(api_key=api_key)


def discover_cursor_models() -> ProviderDiscoverySnapshot:
    provider_id: ProviderId = "cursor"
    blocked = require_probe(provider_id)
    if blocked is not None:
        return blocked

    cred = resolve_credential(provider_id)
    if cred is None:
        return unavailable_snapshot(
            provider_id,
            failure="not_authenticated",
            message="cursor is not authenticated",
        )

    try:
        raw_models = _list_cursor_sdk_models(cred.token)
    except ImportError:
        return unavailable_snapshot(
            provider_id,
            failure="not_installed",
            message="cursor is not installed",
        )
    except Exception as exc:
        return unavailable_snapshot(
            provider_id,
            failure="api_error",
            message=sanitize_provider_error(exc),
        )

    models = []
    for item in raw_models:
        model_id = normalize_model_id(getattr(item, "id", None))
        if model_id is None:
            continue
        reasoning = reasoning_from_cursor_parameters(
            parameters=getattr(item, "parameters", ()) or (),
            variants=getattr(item, "variants", ()) or (),
        )
        models.append(
            discovered_model(
                model_id=model_id,
                display_name=normalize_display_name(
                    model_id, getattr(item, "display_name", None)
                ),
                reasoning=reasoning,
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
