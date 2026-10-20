"""SDK adapter: run_role, validation, and error classification."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from cursor_sdk import CloudAgentOptions, CursorAgentError as SdkCursorAgentError
from cursor_sdk import RunResult
from cursor_sdk import AsyncAgent, AsyncClient

from cascade.agent import (
    CursorAgentError,
    ProviderNotAuthenticatedError,
    RoleResult,
    RoleTurn,
    build_agent_options,
    reject_cloud_runtime,
    run_role,
    validate_model_id,
)
from cascade.agent.adapter import _cursor_bridge_command


def _turn(**overrides: object) -> RoleTurn:
    base = {
        "role": "swe",
        "provider": "cursor",
        "model_id": "composer-2.5",
        "prompt": "do work",
        "cwd": Path("/tmp/worktree"),
        "tools": [],
    }
    base.update(overrides)
    return RoleTurn(**base)  # type: ignore[arg-type]


@pytest.fixture
def api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_test_key")


@pytest.fixture
def mock_async_client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    client = AsyncMock(name="async_client")

    async def launch_bridge(**kwargs: object) -> AsyncMock:
        return client

    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(AsyncClient, "launch_bridge", launch_bridge)
    return client


@pytest.mark.parametrize("model_id", ["", "   ", "\t\n"])
def test_blank_model_id_raises_before_sdk(
    model_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn = _turn(model_id=model_id)
    with pytest.raises(ValueError, match="model_id"):
        validate_model_id(turn.model_id)

    prompt = AsyncMock()
    monkeypatch.setattr(AsyncAgent, "prompt", prompt)
    with pytest.raises(ValueError, match="model_id"):
        asyncio.run(run_role(turn))
    prompt.assert_not_called()


def test_cloud_runtime_rejected() -> None:
    with pytest.raises(TypeError, match="cloud agent runtime"):
        reject_cloud_runtime(cloud=CloudAgentOptions(repos=[]))


def test_cursor_bridge_command_tracks_node_instead_of_shell_wrapper() -> None:
    command = _cursor_bridge_command()
    assert command is not None
    assert command[0].endswith("/node")
    assert command[1].endswith("/dist/bin/cursor-sdk-bridge.js")


def test_startup_error_is_typed_not_role_result(
    api_key_env: None,
    mock_async_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_prompt(*args: object, **kwargs: object) -> RunResult:
        raise SdkCursorAgentError("auth failed", is_retryable=True)

    monkeypatch.setattr(AsyncAgent, "prompt", fail_prompt)

    with pytest.raises(CursorAgentError) as exc_info:
        asyncio.run(run_role(_turn()))

    assert exc_info.value.retryable is True
    assert "auth failed" in str(exc_info.value)


def test_run_error_returns_role_result(
    api_key_env: None,
    mock_async_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def error_prompt(*args: object, **kwargs: object) -> RunResult:
        return RunResult(
            id="run-1",
            agent_id="agent-1",
            status="error",
            result="something broke",
        )

    monkeypatch.setattr(AsyncAgent, "prompt", error_prompt)

    result = asyncio.run(run_role(_turn()))
    assert result.status == "error"
    assert result.text == "something broke"
    assert result.tool_effects == []


def test_agent_disposed_before_return(
    api_key_env: None,
    mock_async_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exited: list[bool] = []

    async def ok_prompt(*args: object, **kwargs: object) -> RunResult:
        return RunResult(
            id="run-2",
            agent_id="agent-2",
            status="finished",
            result="ok",
        )

    async def track_exit(*args: object, **kwargs: object) -> None:
        exited.append(True)

    mock_async_client.__aexit__ = AsyncMock(side_effect=track_exit)
    monkeypatch.setattr(AsyncAgent, "prompt", ok_prompt)

    result = asyncio.run(run_role(_turn()))
    assert result.status == "finished"
    assert exited == [True]


def test_model_id_forwarded_verbatim(
    api_key_env: None,
    mock_async_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    async def capture_prompt(
        message: str,
        options: object,
        *,
        client: AsyncMock,
    ) -> RunResult:
        captured.append(options)
        return RunResult(
            id="run-3",
            agent_id="agent-3",
            status="finished",
            result="done",
        )

    monkeypatch.setattr(AsyncAgent, "prompt", capture_prompt)

    model_id = "  custom-model-id-with-spaces  "
    asyncio.run(run_role(_turn(model_id=model_id)))

    assert len(captured) == 1
    options = captured[0]
    assert getattr(options, "model", None) == model_id


def test_build_agent_options_uses_env_key(api_key_env: None) -> None:
    opts = build_agent_options(_turn(), api_key="cursor_test_key")
    assert opts.api_key == "cursor_test_key"
    assert opts.model == "composer-2.5"
    assert opts.cloud is None
    assert opts.local is not None
    assert opts.local.setting_sources == []
    assert opts.tools == []


def test_build_agent_options_disables_builtin_tools(api_key_env: None) -> None:
    from cursor_sdk import CustomTool

    opts = build_agent_options(_turn(), api_key="cursor_test_key")
    assert opts.tools == []

    turn_custom = _turn(
        role="epic_manager",
        custom_tools={"read_doc": CustomTool(execute=lambda _a, _c: "ok")},
    )
    opts_custom = build_agent_options(turn_custom, api_key="cursor_test_key")
    assert opts_custom.tools is None


def test_non_empty_tools_list_raises_type_error(api_key_env: None) -> None:
    with pytest.raises(TypeError, match="non-empty list"):
        build_agent_options(_turn(tools=["bad"]), api_key="cursor_test_key")


def test_missing_credential_raises_before_launch_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(
        "cascade.agent.adapter.resolve_credential",
        lambda _provider: None,
    )
    launch = AsyncMock()
    monkeypatch.setattr(AsyncClient, "launch_bridge", launch)

    with pytest.raises(ProviderNotAuthenticatedError, match="credential"):
        asyncio.run(run_role(_turn()))

    launch.assert_not_called()


def test_blank_env_credential_raises_before_launch_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "   ")
    monkeypatch.setattr(
        "cascade.agent.adapter.resolve_credential",
        lambda _provider: None,
    )
    launch = AsyncMock()
    monkeypatch.setattr(AsyncClient, "launch_bridge", launch)

    with pytest.raises(ProviderNotAuthenticatedError, match="credential"):
        asyncio.run(run_role(_turn()))

    launch.assert_not_called()


def test_claude_provider_routes_to_cli_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = AsyncMock(return_value=RoleResult(text="cli ok", status="finished"))
    monkeypatch.setattr("cascade.agent.claude_cli.run_claude_role", cli)
    turn = _turn(provider="claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda pid: type("S", (), {"installed": True, "id": pid})(),
    )
    result = asyncio.run(run_role(turn))
    assert result.text == "cli ok"
    cli.assert_awaited_once()


def test_planning_role_enables_local_sandbox(api_key_env: None) -> None:
    from cursor_sdk import CustomTool

    turn_tools = _turn(
        role="epic_manager",
        tools={"cascade": {"command": "true"}},
    )
    opts_tools = build_agent_options(turn_tools, api_key="cursor_test_key")
    assert opts_tools.local is not None
    assert opts_tools.local.sandbox_options is None

    turn_custom = _turn(
        role="epic_manager",
        custom_tools={"read_doc": CustomTool(execute=lambda _a, _c: "ok")},
    )
    opts_custom = build_agent_options(turn_custom, api_key="cursor_test_key")
    assert opts_custom.local.sandbox_options is None
    assert opts_custom.mcp_servers is None
    assert opts_custom.local.custom_tools is not None

    turn_no_mcp = _turn(role="epic_manager", tools=[])
    opts_no_mcp = build_agent_options(turn_no_mcp, api_key="cursor_test_key")
    assert opts_no_mcp.local.sandbox_options is not None
    assert opts_no_mcp.local.sandbox_options.enabled is True
