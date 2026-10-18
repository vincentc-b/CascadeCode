"""Boss read models (dispatchable sets, slots, failures)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cascade.boss.view import BossView, compute_boss_view

__all__ = ["BossView", "compute_boss_view"]


def __getattr__(name: str):
    if name in __all__:
        from cascade.boss import view as view_mod

        return getattr(view_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
