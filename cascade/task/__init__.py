"""Task Team LangGraph runtime (local checkpoint, boot hook).

Keep graph and boot imports lazy: audit observers import task.lifecycle_lock
while watchdog.model_resolve is still initializing in a fresh process.
"""

from importlib import import_module

from cascade.task.registry import clear_task_tools, register_task_tool, task_tools
from cascade.task.state import TaskGraphState

_LAZY_EXPORTS = {
    "boot_task": "boot",
    "fail_closed_boot": "boot",
    "install_task_boot_hook": "boot",
    "last_fail_closed_boot": "boot",
    "ensure_task_graph": "graph",
    "ingest_queue": "graph",
    "invoke_tool": "graph",
}


def __getattr__(name: str):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"cascade.task.{module}"), name)

__all__ = [
    "TaskGraphState",
    "boot_task",
    "clear_task_tools",
    "ensure_task_graph",
    "fail_closed_boot",
    "ingest_queue",
    "install_task_boot_hook",
    "invoke_tool",
    "last_fail_closed_boot",
    "register_task_tool",
    "task_tools",
]
