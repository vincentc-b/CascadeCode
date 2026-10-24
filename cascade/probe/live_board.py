"""Detect production board roots that must never be probe mutation targets."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from cascade.board.paths import infer_repo_root
from cascade.probe.errors import ProbeError

_ENV_LIVE_BOARD_ROOT = "CASCADE_LIVE_BOARD_ROOT"


@lru_cache(maxsize=1)
def live_board_roots() -> tuple[Path, ...]:
    """Resolved roots whose board trees the disposable probe must not mutate."""

    roots: list[Path] = []
    env = os.environ.get(_ENV_LIVE_BOARD_ROOT, "").strip()
    if env:
        roots.append(Path(env).resolve())

    package_dir = Path(__file__).resolve().parents[1]
    source_root = package_dir.parent.resolve()
    if (source_root / "docs" / "epics").is_dir():
        roots.append(source_root)

    deduped: list[Path] = []
    for root in roots:
        if root not in deduped:
            deduped.append(root)
    return tuple(deduped)


def is_live_board_path(path: Path) -> bool:
    """True when ``path`` is a live board root or inside one."""

    resolved = Path(path).resolve()
    for live in live_board_roots():
        if resolved == live or live in resolved.parents:
            return True
    repo = infer_repo_root(resolved)
    if repo is not None:
        repo = repo.resolve()
        for live in live_board_roots():
            if repo == live:
                return True
    return False


def reject_live_board_mutation_target(path: Path) -> None:
    """Raise when ``path`` would mutate the operator production board."""

    if is_live_board_path(path):
        raise ProbeError(f"live board path cannot be a probe mutation target: {path}")
