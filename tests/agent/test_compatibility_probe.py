"""Compatibility evidence must come from observed launch interfaces."""

from cascade.agent.discovery import compatibility


def test_missing_cli_help_does_not_verify_support(monkeypatch) -> None:
    monkeypatch.setattr(compatibility, "_help", lambda *_args: None)

    evidence = compatibility.probe_provider_compatibility("codex")

    assert evidence.cli_compatible is None
    assert evidence.required_tool_host_compatible is None
    assert evidence.sdk_compatible is True  # The CLI path does not use this SDK.


def test_documented_cli_without_mcp_is_incompatible(monkeypatch) -> None:
    monkeypatch.setattr(
        compatibility,
        "_help",
        lambda _binary, *args: (
            "Usage: codex exec --config value" if args == ("exec",) else "Usage: codex"
        ),
    )

    evidence = compatibility.probe_provider_compatibility("codex")

    assert evidence.cli_compatible is True
    assert evidence.required_tool_host_compatible is False
