"""OpenAI Codex CLI model catalog discovery."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Mapping

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

CODEX_BINARY = "codex"


def _run_codex_debug_models() -> Mapping[str, Any]:
    binary = shutil.which(CODEX_BINARY)
    if binary is None:
        raise FileNotFoundError(CODEX_BINARY)
    proc = subprocess.run(
        [binary, "debug", "models"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError("codex debug models failed")
    payload = json.loads(proc.stdout)
    if not isinstance(payload, Mapping):
        raise TypeError("codex model catalog must be a JSON object")
    return payload


def _codex_models_from_payload(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    out: list[Mapping[str, Any]] = []
    for item in models:
        if isinstance(item, Mapping):
            out.append(item)
    return out


def _include_codex_model(record: Mapping[str, Any]) -> bool:
    visibility = record.get("visibility")
    if visibility == "hidden":
        return False
    supported = record.get("supported_in_api")
    if supported is False:
        return False
    return normalize_model_id(record.get("slug")) is not None


def discover_codex_models() -> ProviderDiscoverySnapshot:
    provider_id: ProviderId = "codex"
    blocked = require_probe(provider_id)
    if blocked is not None:
        return blocked

    try:
        payload = _run_codex_debug_models()
    except Exception as exc:
        return unavailable_snapshot(
            provider_id,
            failure="api_error",
            message=sanitize_provider_error(exc),
        )

    models = []
    for record in _codex_models_from_payload(payload):
        if not _include_codex_model(record):
            continue
        model_id = normalize_model_id(record.get("slug"))
        assert model_id is not None
        models.append(
            discovered_model(
                model_id=model_id,
                display_name=normalize_display_name(
                    model_id, record.get("display_name")
                ),
                reasoning=reasoning_from_codex_record(record),
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
        # This integration can pass OpenAI service-tier config to Codex CLI.
        supports_flex_mode=True,
    )
