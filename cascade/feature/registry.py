"""Feature tool registry (implementations registered by later tasks)."""

from __future__ import annotations

from collections.abc import Callable

_tools: dict[str, Callable[..., object]] = {}


def register_feature_tool(name: str, fn: Callable[..., object]) -> None:
    _tools[name] = fn


def feature_tools() -> dict[str, Callable[..., object]]:
    return dict(_tools)


def clear_feature_tools() -> None:
    _tools.clear()
