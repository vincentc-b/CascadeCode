"""Structured pass/fail for disposable lifecycle probe runs (feat_012_003)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProbePhaseResult:
    """Outcome for one exercised probe phase."""

    phase: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class LifecycleProbeReport:
    """Aggregate result for a full synthetic lifecycle probe invocation."""

    ok: bool
    phases: tuple[ProbePhaseResult, ...]

    @property
    def failing_phase(self) -> str | None:
        for row in self.phases:
            if not row.ok:
                return row.phase
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "failing_phase": self.failing_phase,
            "phases": [
                {"phase": row.phase, "ok": row.ok, "detail": row.detail}
                for row in self.phases
            ],
        }


def merge_phase_results(*groups: tuple[ProbePhaseResult, ...]) -> LifecycleProbeReport:
    phases = tuple(row for group in groups for row in group)
    ok = all(row.ok for row in phases)
    return LifecycleProbeReport(ok=ok, phases=phases)
