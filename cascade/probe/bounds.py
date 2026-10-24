"""Bounded execution controls for disposable probe runs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from cascade.probe.errors import ProbeTimeoutError

_DEFAULT_MAX_SECONDS = 300.0
_ENV_MAX_SECONDS = "CASCADE_PROBE_MAX_SECONDS"


@dataclass(frozen=True, slots=True)
class ProbeExecutionBounds:
    """Monotonic deadline for a single probe invocation."""

    max_seconds: float = _DEFAULT_MAX_SECONDS

    @classmethod
    def from_env(cls) -> ProbeExecutionBounds:
        raw = os.environ.get(_ENV_MAX_SECONDS, "").strip()
        if not raw:
            return cls()
        try:
            value = float(raw)
        except ValueError as exc:
            raise ProbeTimeoutError(
                f"invalid {_ENV_MAX_SECONDS}: {raw!r}"
            ) from exc
        if value <= 0:
            raise ProbeTimeoutError(f"{_ENV_MAX_SECONDS} must be positive")
        return cls(max_seconds=value)

    def deadline(self, *, start: float | None = None) -> "ProbeDeadline":
        return ProbeDeadline(start=start or time.monotonic(), max_seconds=self.max_seconds)


@dataclass(slots=True)
class ProbeDeadline:
    """Injected-clock friendly monotonic deadline (no sleeping)."""

    start: float
    max_seconds: float

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def remaining(self) -> float:
        return self.max_seconds - self.elapsed()

    def check(self, *, phase: str = "probe") -> None:
        if self.remaining() < 0:
            raise ProbeTimeoutError(
                f"{phase} exceeded bounded execution ({self.max_seconds:.0f}s)"
            )
