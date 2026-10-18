"""resolve_backend provider selection and fail-closed behavior."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from cascade.board.types import WorkMeta
from cascade.watchdog.model_resolve import (
    ModelConfigError,
    ResolvedBackend,
    ResolvedModel,
    resolve_backend,
)
from tests.support import make_repo


def _write_providers(root: Path, toml_body: str) -> None:
    (root / "cascade.toml").write_text(toml_body.strip() + "\n", encoding="utf-8")


def _task_meta(root: Path, *, provider: str | None = None) -> WorkMeta:
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
        provider=provider,  # type: ignore[arg-type]
    )


def test_document_provider_override(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_providers(
        root,
        """
[providers]
default = "cursor"

[providers.cursor]
task = "cursor-task"

[providers.claude]
task = "claude-task"
""",
    )
    meta = _task_meta(root, provider="claude")
    backend = resolve_backend("swe", meta, root=root)
    assert backend == ResolvedBackend(
        provider="claude",
        provider_source="document",
        model=ResolvedModel(role="swe", model_id="claude-task", source="project-tier"),
    )


def test_project_default_provider_legacy_models(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_providers(
        root,
        """
[models]
task = "legacy-task"
""",
    )
    backend = resolve_backend("swe", None, root=root)
    assert backend == ResolvedBackend(
        provider="cursor",
        provider_source="project-default",
        model=ResolvedModel(role="swe", model_id="legacy-task", source="project-tier"),
    )


def test_missing_tier_on_selected_provider_fails_closed(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _write_providers(
        root,
        """
[providers]
default = "claude"

[providers.cursor]
task = "only-cursor"
""",
    )
    with pytest.raises(ModelConfigError):
        resolve_backend("swe", None, root=root)
