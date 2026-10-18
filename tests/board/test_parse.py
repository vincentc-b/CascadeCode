"""parse_doc reads frontmatter and leaves the body intact."""

from pathlib import Path

import pytest

from cascade.agent.errors import ProviderConfigError
from cascade.board import SchemaError, parse_doc
from cascade.board.parse import parse_text, render_doc

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_happy_epic() -> None:
    path = FIXTURES / "docs" / "epics" / "1_backlog" / "epic_001_ok.md"
    doc = parse_doc(path)
    assert doc.meta.id == "epic_001"
    assert doc.meta.tier == "epic"
    assert doc.meta.status == "backlog"
    assert doc.meta.parent is None
    assert doc.meta.parent_rev is None
    assert doc.meta.path == path.resolve()
    assert doc.sha is None
    assert "## Intent" in doc.body
    assert "## Amendment log" in doc.body

    again = parse_text(render_doc(doc), doc.meta.path)
    assert again.body == doc.body
    assert again.meta.id == doc.meta.id
    assert again.meta.title == doc.meta.title
    assert again.meta.created == doc.meta.created
    assert again.meta.skills == []
    assert doc.meta.model is None
    assert doc.meta.models is None
    assert doc.meta.provider is None
    rendered = render_doc(doc)
    assert "\nmodel:" not in rendered
    assert "\nmodels:" not in rendered
    assert "\nprovider:" not in rendered


def test_parse_round_trip_with_model_frontmatter() -> None:
    path = FIXTURES / "docs" / "epics" / "1_backlog" / "epic_003_model.md"
    doc = parse_doc(path)
    assert doc.meta.model == "epic-tier-model"
    assert doc.meta.models == {"epic_architect": "role-specific-model"}
    again = parse_text(render_doc(doc), path)
    assert again.meta.model == doc.meta.model
    assert again.meta.models == doc.meta.models
    rendered = render_doc(doc)
    assert "model: epic-tier-model" in rendered
    assert "epic_architect: role-specific-model" in rendered


def test_empty_models_mapping_round_trips_as_omitted() -> None:
    base = FIXTURES / "docs" / "epics" / "1_backlog" / "epic_001_ok.md"
    doc = parse_doc(base)
    rendered = render_doc(doc)
    parts = rendered.split("---", 2)
    fm = parts[1].rstrip("\n")
    body = parts[2] if len(parts) > 2 else doc.body
    text = f"---\n{fm}\nmodels: {{}}\n---\n{body}"
    parsed = parse_text(text, base)
    assert parsed.meta.models is None
    assert "\nmodels:" not in render_doc(parsed)


def test_parse_round_trip_with_provider_frontmatter() -> None:
    base = FIXTURES / "docs" / "epics" / "1_backlog" / "epic_001_ok.md"
    doc = parse_doc(base)
    rendered = render_doc(doc)
    parts = rendered.split("---", 2)
    fm = parts[1].rstrip("\n")
    body = parts[2] if len(parts) > 2 else doc.body
    text = f"---\n{fm}\nprovider: claude\n---\n{body}"
    parsed = parse_text(text, base)
    assert parsed.meta.provider == "claude"
    again = parse_text(render_doc(parsed), base)
    assert again.meta.provider == "claude"
    assert "provider: claude" in render_doc(parsed)


def test_invalid_provider_frontmatter_raises() -> None:
    base = FIXTURES / "docs" / "epics" / "1_backlog" / "epic_001_ok.md"
    doc = parse_doc(base)

    def with_extra(yaml_line: str) -> str:
        rendered = render_doc(doc)
        parts = rendered.split("---", 2)
        fm = parts[1].rstrip("\n")
        body = parts[2] if len(parts) > 2 else doc.body
        return f"---\n{fm}\n{yaml_line}\n---\n{body}"

    with pytest.raises(SchemaError, match="provider must be a non-blank string"):
        parse_text(with_extra("provider: ''"), base)

    with pytest.raises(ProviderConfigError, match="unknown provider"):
        parse_text(with_extra("provider: unknown-vendor"), base)


def test_invalid_model_frontmatter_raises() -> None:
    base = FIXTURES / "docs" / "epics" / "1_backlog" / "epic_001_ok.md"
    doc = parse_doc(base)

    def with_extra(yaml_line: str) -> str:
        rendered = render_doc(doc)
        parts = rendered.split("---", 2)
        fm = parts[1].rstrip("\n")
        body = parts[2] if len(parts) > 2 else doc.body
        return f"---\n{fm}\n{yaml_line}\n---\n{body}"

    with pytest.raises(SchemaError, match="model must be a non-blank string"):
        parse_text(with_extra("model: ''"), base)

    with pytest.raises(SchemaError, match="model must be a non-blank string"):
        parse_text(with_extra("model: 1"), base)

    with pytest.raises(SchemaError, match="models must be a mapping"):
        parse_text(with_extra("models: []"), base)

    with pytest.raises(SchemaError, match="non-blank string"):
        parse_text(with_extra("models:\n  epic_manager: '  '"), base)


def test_missing_frontmatter_raises() -> None:
    with pytest.raises(SchemaError):
        parse_doc(FIXTURES / "bad_no_frontmatter.md")


def test_invalid_yaml_raises() -> None:
    with pytest.raises(SchemaError):
        parse_doc(FIXTURES / "bad_yaml.md")
