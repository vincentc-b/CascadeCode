"""resolve_model precedence and fail-closed behavior."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from cascade.agent.types import RoleId
from cascade.board.types import WorkMeta
from cascade.watchdog.config import ConfigError
from cascade.watchdog.model_resolve import (
    ModelConfigError,
    ResolvedModel,
    resolve_model,
)
from tests.support import add_doc, make_repo

_ALL_ROLES: tuple[RoleId, ...] = (
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
    "boss",
)

_TIER_DEFAULTS = """
[models]
epic = "proj-epic"
feature = "proj-feature"
task = "proj-task"
boss = "proj-boss"
""".strip()


def _write_models(root: Path, toml_body: str) -> None:
    (root / "cascade.toml").write_text(toml_body.strip() + "\n", encoding="utf-8")


def _task_meta(root: Path) -> WorkMeta:
    """In-memory task WorkMeta for resolver tests (no board write)."""

    return WorkMeta(
        id="task_001",
        title="Task",
        tier="task",
        status="backlog",
        parent="feat_001",
        children=[],
        depends_on=[],
        owners=["tester"],
        skills=[],
        parent_rev=None,
        created=date(2026, 10, 9),
        updated=date(2026, 10, 9),
        path=root / "docs/tasks/1_backlog/task_001_task.md",
    )


def test_project_tier_default_for_each_role_without_doc(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(root, _TIER_DEFAULTS)

    expected = {
        "epic_manager": ("proj-epic", "project-tier"),
        "epic_architect": ("proj-epic", "project-tier"),
        "feature_lead": ("proj-feature", "project-tier"),
        "feature_architect": ("proj-feature", "project-tier"),
        "swe": ("proj-task", "project-tier"),
        "boss": ("proj-boss", "project-tier"),
    }
    for role in _ALL_ROLES:
        resolved = resolve_model(role, None, root=root, provider="cursor")
        model_id, source = expected[role]
        assert resolved == ResolvedModel(role=role, model_id=model_id, source=source)


def test_document_model_beats_project_defaults(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(root, _TIER_DEFAULTS)
    meta = replace(_task_meta(root), model="doc-model")

    resolved = resolve_model("swe", meta, root=root, provider="cursor")
    assert resolved == ResolvedModel(
        role="swe", model_id="doc-model", source="document"
    )


def test_document_role_beats_document_model_and_project(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(root, _TIER_DEFAULTS)
    meta = replace(
        _task_meta(root),
        model="doc-model",
        models={"swe": "role-model"},
    )

    resolved = resolve_model("swe", meta, root=root, provider="cursor")
    assert resolved == ResolvedModel(
        role="swe", model_id="role-model", source="document-role"
    )


def test_project_role_beats_tier_key(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[models]
epic = "tier-epic"
task = "tier-task"

[models.roles]
epic_architect = "role-epic-architect"
swe = "role-swe"
""",
    )

    assert resolve_model("epic_architect", None, root=root, provider="cursor") == ResolvedModel(
        role="epic_architect",
        model_id="role-epic-architect",
        source="project-role",
    )
    assert resolve_model("swe", None, root=root, provider="cursor") == ResolvedModel(
        role="swe", model_id="role-swe", source="project-role"
    )


def test_boss_uses_models_boss_when_set(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[models]
epic = "proj-epic"
boss = "proj-boss-only"
""",
    )
    resolved = resolve_model("boss", None, root=root, provider="cursor")
    assert resolved == ResolvedModel(
        role="boss", model_id="proj-boss-only", source="project-tier"
    )


def test_boss_falls_back_to_epic_when_boss_key_absent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[models]
epic = "epic-for-boss"
feature = "proj-feature"
task = "proj-task"
""",
    )
    resolved = resolve_model("boss", None, root=root, provider="cursor")
    assert resolved == ResolvedModel(
        role="boss",
        model_id="epic-for-boss",
        source="boss-falls-back-to-epic",
    )


def test_missing_tier_default_raises_without_doc_override(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[models]
epic = "only-epic"
""",
    )
    with pytest.raises(ModelConfigError):
        resolve_model("swe", None, root=root, provider="cursor")


def test_absent_models_table_raises_at_resolve_time(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    with pytest.raises(ModelConfigError):
        resolve_model("swe", None, root=root, provider="cursor")


def test_auto_passes_through_from_toml_and_frontmatter(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[models]
task = "auto"

[models.roles]
swe = "auto"
""",
    )
    assert resolve_model("swe", None, root=root, provider="cursor").model_id == "auto"

    meta = replace(_task_meta(root), model="auto")
    assert resolve_model("swe", meta, root=root, provider="cursor") == ResolvedModel(
        role="swe", model_id="auto", source="document"
    )


def test_invalid_toml_stays_config_error(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text("[models\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        resolve_model("swe", None, root=root, provider="cursor")


def test_blank_document_fields_fall_through_to_project(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(root, _TIER_DEFAULTS)
    meta = replace(
        _task_meta(root),
        model="  ",
        models={"swe": "\t"},
    )
    resolved = resolve_model("swe", meta, root=root, provider="cursor")
    assert resolved == ResolvedModel(
        role="swe", model_id="proj-task", source="project-tier"
    )


def test_same_role_differs_by_provider_table(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[providers]
default = "cursor"

[providers.cursor]
task = "cursor-task-model"

[providers.claude]
task = "claude-task-model"
""",
    )
    cursor = resolve_model("swe", None, root=root, provider="cursor")
    claude = resolve_model("swe", None, root=root, provider="claude")
    assert cursor.model_id == "cursor-task-model"
    assert claude.model_id == "claude-task-model"


def test_feature_doc_model_does_not_use_epic_parent_meta(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[providers]
default = "cursor"

[providers.cursor]
feature = "proj-feature"
task = "proj-task"
""",
    )
    epic_meta = replace(
        add_doc(root, id="epic_001", title="Epic", tier="epic").meta,
        model="epic-only",
    )
    feature_meta = replace(
        add_doc(
            root,
            id="feat_001",
            title="Feature",
            tier="feature",
            parent="epic_001",
        ).meta,
        model="feature-doc-model",
    )
    resolved = resolve_model("feature_lead", feature_meta, root=root, provider="cursor")
    assert resolved == ResolvedModel(
        role="feature_lead",
        model_id="feature-doc-model",
        source="document",
    )
    assert epic_meta.model == "epic-only"


def test_boss_ignores_document_override_when_doc_passed(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_models(
        root,
        """
[models]
epic = "proj-epic"
""",
    )
    epic_meta = add_doc(root, id="epic_001", title="Epic", tier="epic").meta
    epic_meta = replace(epic_meta, model="boss-doc-override")
    resolved = resolve_model("boss", epic_meta, root=root, provider="cursor")
    assert resolved == ResolvedModel(
        role="boss",
        model_id="proj-epic",
        source="boss-falls-back-to-epic",
    )
