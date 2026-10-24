"""Inventory-backed brief default validation (task_006_002_001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.agent.discovery.inventory import clear_provider_inventory_cache, get_provider_inventory
from cascade.agent.discovery.types import DiscoveredModel, ProviderDiscoverySnapshot, ReasoningCapability
from cascade.briefs import build_brief_doc, brief_template, validate_brief
from cascade.brief_stack import brief_selection_from_meta
from tests.agent.test_provider_inventory import _available, _fake_discover, _unavailable
from tests.support import make_repo


def _stack_models(**overrides: str) -> dict[str, str]:
    base = {
        "epic_manager": "gpt-manager",
        "epic_architect": "gpt-architect",
        "feature_lead": "gpt-feature-lead",
        "feature_architect": "gpt-feature-architect",
        "swe": "gpt-swe",
    }
    base.update(overrides)
    return base


def _codex_inventory(**overrides: str) -> dict[str, ProviderDiscoverySnapshot]:
    reasoning = ReasoningCapability(default_level="medium", override_levels=("low", "high"))
    models = _stack_models(**overrides)
    return {
        "cursor": _unavailable("cursor", failure="not_installed"),
        "claude": _unavailable("claude", failure="not_authenticated"),
        "codex": ProviderDiscoverySnapshot(
            provider_id="codex",
            available=True,
            models=tuple(
                DiscoveredModel(
                    id=model_id,
                    display_name=model_id,
                    reasoning=reasoning if model_id == "gpt-swe" else None,
                )
                for model_id in models.values()
            ),
        ),
    }


@pytest.fixture(autouse=True)
def _clear_inventory_cache() -> None:
    clear_provider_inventory_cache()
    yield
    clear_provider_inventory_cache()


@pytest.fixture
def patch_codex_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = _codex_inventory()

    def _get_inventory(**kwargs: object) -> object:
        return get_provider_inventory(
            discover=_fake_discover(mapping),
            ttl_seconds=60.0,
            now=10.0,
            force_refresh=bool(kwargs.get("force_refresh")),
        )

    monkeypatch.setattr("cascade.briefs.get_provider_inventory", _get_inventory)


def _request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Search experience",
        "intent": "Help operators find active work.",
        "success_criteria": "Search returns matching epics and features.",
        "constraints": "No hosted index.",
        "provider": "codex",
        "models": _stack_models(),
    }
    payload.update(overrides)
    return payload


def test_validate_brief_rejects_unknown_model(
    tmp_path: Path, patch_codex_inventory: None
) -> None:
    raw = _request(models=_stack_models(swe="missing-model"))
    with pytest.raises(ValueError, match="not offered"):
        validate_brief(raw, root=tmp_path)


def test_validate_brief_rejects_unsupported_reasoning_override(
    tmp_path: Path, patch_codex_inventory: None
) -> None:
    raw = _request(reasoning={"swe": "turbo"})
    with pytest.raises(ValueError, match="reasoning override"):
        validate_brief(raw, root=tmp_path)


def test_validate_brief_keeps_default_reasoning_implicit(
    tmp_path: Path, patch_codex_inventory: None
) -> None:
    request = validate_brief(_request(reasoning={"swe": "medium"}), root=tmp_path)
    assert request.reasoning == {}


def test_validate_brief_persists_non_default_reasoning(
    tmp_path: Path, patch_codex_inventory: None
) -> None:
    request = validate_brief(_request(reasoning={"swe": "high"}), root=tmp_path)
    assert request.reasoning == {"swe": "high"}


def test_build_brief_doc_persists_full_stack_and_reasoning(
    tmp_path: Path, patch_codex_inventory: None
) -> None:
    request = validate_brief(_request(reasoning={"swe": "low"}), root=tmp_path)
    path = tmp_path / "docs/epics/1_backlog/epic_004_search_experience.md"
    doc = build_brief_doc(request, "epic_004", path)
    assert doc.meta.models == _stack_models()
    assert doc.meta.reasoning == {"swe": "low"}


def test_brief_template_uses_inventory_providers_only(
    tmp_path: Path, patch_codex_inventory: None
) -> None:
    root = make_repo(tmp_path, git=False)
    payload = brief_template(root)
    assert payload["providers"] == ["codex"]
    assert set(payload["models"]) == set(_stack_models())
    assert payload["inventory_available"] is True


def test_brief_template_includes_saved_selection_for_reload(
    tmp_path: Path, patch_codex_inventory: None
) -> None:
    root = make_repo(tmp_path, git=False)
    request = validate_brief(_request(reasoning={"swe": "low"}), root=root)
    path = root / "docs/epics/1_backlog/epic_010_saved.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    from cascade.board.parse import render_doc

    path.write_text(render_doc(build_brief_doc(request, "epic_010", path)), encoding="utf-8")

    payload = brief_template(root, epic_id="epic_010")
    saved = payload["saved"]
    assert saved["provider"] == "codex"
    assert saved["models"]["swe"] == "gpt-swe"
    assert saved["reasoning"] == {"swe": "low"}


def test_brief_selection_from_meta_round_trip(patch_codex_inventory: None, tmp_path: Path) -> None:
    request = validate_brief(_request(reasoning={"swe": "high"}), root=tmp_path)
    doc = build_brief_doc(request, "epic_004", tmp_path / "epic.md")
    payload = brief_selection_from_meta(doc.meta)
    assert payload["manager_model"] == "gpt-manager"
    assert payload["reasoning"] == {"swe": "high"}
