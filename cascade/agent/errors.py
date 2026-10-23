"""Agent provider startup errors (run never started or tool host unavailable)."""

from __future__ import annotations

from cursor_sdk import CursorAgentError as SdkCursorAgentError


class CursorAgentError(Exception):
    """Startup failure before a Cursor agent run executes."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable

    @classmethod
    def from_sdk(cls, err: SdkCursorAgentError) -> CursorAgentError:
        return cls(err.message, retryable=err.is_retryable)


class ProviderConfigError(Exception):
    """Invalid provider id in config or document validation."""


class ProviderNotInstalledError(Exception):
    """Probe reports backend unavailable (not installed)."""


class ProviderNotAuthenticatedError(Exception):
    """Backend installed but no credential source (not authenticated)."""


class ProviderNotImplementedError(Exception):
    """Backend dispatch is not implemented yet."""


class ProviderCliError(Exception):
    """CLI argv, probe, or subprocess setup failure before a turn executes."""


class ProviderToolHostError(Exception):
    """CLI cannot load Cascade MCP tools for this turn (fail closed)."""


class ProviderCliTimeoutError(ProviderCliError):
    """CLI subprocess exceeded the turn timeout."""


class TurnCancelledForDrain(Exception):
    """Model turn ended because the worker entered drain shutdown."""

    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f"turn cancelled for worker drain ({role})")
