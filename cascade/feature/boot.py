"""Feature boot hook: pin parent_rev, compile graph, drain activation queue events."""

from __future__ import annotations

from pathlib import Path

from cascade.board.store import pin_parent, read_doc
from cascade.feature.graph import ingest_queue, seed_feature_role_models
from cascade.watchdog.boot_model import toast_model_config_failure
from cascade.watchdog.config import ConfigError
from cascade.watchdog.hooks import register_boot_hook
from cascade.agent.errors import ProviderConfigError
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend

_boot_root: Path | None = None
_last_model_config_failure: tuple[str, str] | None = None


def last_feature_boot_model_failure() -> tuple[str, str] | None:
    """Return the most recent feature boot model resolution failure, if any."""

    return _last_model_config_failure


def boot_feature(work_id: str) -> None:
    global _last_model_config_failure
    if _boot_root is None:
        raise RuntimeError("install_feature_boot_hook(root) must run before boot_feature")
    from cascade.workspace.integration_worktree import doc_filesystem_root

    try:
        doc_root = doc_filesystem_root(work_id, trunk=_boot_root)
        doc = read_doc(work_id, root=doc_root)
    except Exception:
        _last_model_config_failure = None
        return
    if doc.meta.tier != "feature":
        _last_model_config_failure = None
        return
    try:
        lead = resolve_backend("feature_lead", doc.meta, root=_boot_root)
        architect = resolve_backend("feature_architect", doc.meta, root=_boot_root)
    except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
        _last_model_config_failure = (work_id, str(exc))
        toast_model_config_failure(work_id, str(exc), root=_boot_root)
        return
    _last_model_config_failure = None
    parent = doc.meta.parent
    if parent:
        pin_parent(work_id, parent, root=doc_root)
    seed_feature_role_models(
        work_id,
        lead=lead,
        architect=architect,
        root=_boot_root,
    )
    ingest_queue(work_id, root=_boot_root)


def install_feature_boot_hook(root: Path) -> None:
    """Register the feature boot hook for this repo root (idempotent)."""

    global _boot_root
    _boot_root = Path(root).resolve()
    from cascade.watchdog.hooks import _boot

    if not any(fn is boot_feature for fn in _boot["feature"]):
        register_boot_hook("feature", boot_feature)
