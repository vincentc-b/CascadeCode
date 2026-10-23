"""Probe harness failures (feat_012_003 / task_012_003_001)."""


class ProbeError(Exception):
    """Invalid probe target, lifecycle precondition, or operator input."""


class ProbeTimeoutError(ProbeError):
    """Bounded probe execution exceeded its deadline."""
