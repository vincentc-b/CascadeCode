"""Process-local isolation for probe scenarios (no live agent kickoffs)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory
from cascade.workspace.convergence import reset_convergence_detection_for_tests


@contextmanager
def isolated_probe_scenario() -> Iterator[None]:
    """Reset watchdog/convergence memory and stub queue delivery for one probe run."""

    clear_hooks()
    clear_watchdog_memory()
    reset_convergence_detection_for_tests()

    import cascade.automation as automation
    import cascade.workspace.kickoff as kickoff

    original_kickoff: Callable[..., Any] = kickoff.deliver_queue_kickoffs
    original_advance: Callable[..., Any] = automation.advance_work

    kickoff.deliver_queue_kickoffs = lambda _root: None  # type: ignore[method-assign]
    automation.advance_work = lambda _root: {"features": [], "tasks": []}  # type: ignore[method-assign]
    try:
        yield
    finally:
        kickoff.deliver_queue_kickoffs = original_kickoff  # type: ignore[method-assign]
        automation.advance_work = original_advance  # type: ignore[method-assign]
        clear_hooks()
        clear_watchdog_memory()
        reset_convergence_detection_for_tests()
