"""Epic boot hook: compile graph and drain activation queue events."""

from __future__ import annotations

from pathlib import Path

from cascade.board.store import read_doc
from cascade.epic.graph import seed_epic_role_models
from cascade.watchdog.boot_model import toast_model_config_failure
from cascade.watchdog.config import ConfigError
from cascade.watchdog.hooks import register_boot_hook
from cascade.agent.errors import ProviderConfigError
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend

_boot_root: Path | None = None
_last_model_config_failure: tuple[str, str] | None = None


def last_epic_boot_model_failure() -> tuple[str, str] | None:
    """Return the most recent epic boot model resolution failure, if any."""

    return _last_model_config_failure


def boot_epic(work_id: str) -> None:
    global _last_model_config_failure
    if _boot_root is None:
        raise RuntimeError("install_epic_boot_hook(root) must run before boot_epic")
    from cascade.workspace.integration_worktree import doc_filesystem_root

    try:
        doc_root = doc_filesystem_root(work_id, trunk=_boot_root)
        doc = read_doc(work_id, root=doc_root)
    except Exception:
        _last_model_config_failure = None
        return
    if doc.meta.tier != "epic":
        _last_model_config_failure = None
        return
    try:
        manager = resolve_backend("epic_manager", doc.meta, root=_boot_root)
        architect = resolve_backend("epic_architect", doc.meta, root=_boot_root)
    except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
        _last_model_config_failure = (work_id, str(exc))
        toast_model_config_failure(work_id, str(exc), root=_boot_root)
        return
    _last_model_config_failure = None
    seed_epic_role_models(
        work_id,
        manager=manager,
        architect=architect,
        root=_boot_root,
    )


def install_epic_boot_hook(root: Path) -> None:
    """Register the epic boot hook for this repo root (idempotent)."""

    global _boot_root
    _boot_root = Path(root).resolve()
    from cascade.watchdog.hooks import _boot

    if not any(fn is boot_epic for fn in _boot["epic"]):
        register_boot_hook("epic", boot_epic)
