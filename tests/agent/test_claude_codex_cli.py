"""Claude/Codex CLI adapters (task_074)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
import pytest

from cascade.agent.claude_cli import build_claude_argv, run_claude_role
from cascade.agent.codex_cli import build_codex_argv, run_codex_role
from cascade.agent.cli_common import (
    assert_claude_non_interactive,
    assert_codex_non_interactive,
    run_subprocess_turn,
)
from cascade.agent.errors import ProviderCliError, ProviderToolHostError
from cascade.agent.types import RoleResult, RoleTurn

_CLAUDE_HELP = """
Usage: claude [options]
  -p, --print                 Print response without interactive mode
  --output-format             text, json, stream-json
  --model                     model id
  --mcp-config                Load MCP servers from JSON files
  --strict-mcp-config         Only use MCP servers from --mcp-config
"""

_CODEX_EXEC_HELP = """
Usage: codex exec [options] [PROMPT]
  -c, --config key=value      Inline configuration override
  --model, -m                 Override model
  --color always|never|auto
  --approve-for-me            Automatic approval review
  --skip-git-repo-check       Allow running outside a Git repository
  --ignore-user-config        Ignore user config but retain authentication
  PROMPT use - for stdin
"""

_CODEX_MCP_HELP = """
Usage: codex mcp [command]
  Manage Model Context Protocol server entries
"""


def _turn(**overrides: object) -> RoleTurn:
    base = {
        "role": "swe",
        "provider": "claude",
        "model_id": "claude-sonnet-4-6",
        "prompt": "implement feature",
        "cwd": Path("/tmp/worktree"),
        "tools": [],
    }
    base.update(overrides)
    return RoleTurn(**base)  # type: ignore[arg-type]


def _mcp_tools() -> dict[str, dict[str, object]]:
    return {
        "cascade": {
            "command": sys.executable,
            "args": ["-m", "cascade.agent.mcp_stdio"],
            "env": {"CASCADE_MCP_CONFIG": "/scratch/.cascade_mcp.json"},
            "cwd": "/repo",
        }
    }


@pytest.fixture
def mock_help(monkeypatch: pytest.MonkeyPatch) -> None:
    import cascade.agent.cli_common as cli_common

    cli_common._help_cache.clear()

    async def fake_help(binary: str, *prefix: str) -> str:
        if binary == "claude":
            return _CLAUDE_HELP
        if binary == "codex" and prefix == ("exec",):
            return _CODEX_EXEC_HELP
        if binary == "codex" and prefix == ("mcp",):
            return _CODEX_MCP_HELP
        raise AssertionError(f"unexpected help probe: {binary} {prefix}")

    for target in (
        "cascade.agent.cli_common.read_cli_help",
        "cascade.agent.claude_cli.read_cli_help",
        "cascade.agent.codex_cli.read_cli_help",
    ):
        monkeypatch.setattr(target, fake_help)


class _FakeProc:
    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.pid = None
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self, _stdin: bytes | None = None) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return self.returncode


def test_claude_prompt_cwd_and_wait(mock_help: None, monkeypatch: pytest.MonkeyPatch) -> None:
    cwd = Path("/tmp/scratch-epic")
    cwd.mkdir(parents=True, exist_ok=True)
    turn = _turn(cwd=cwd, tools=_mcp_tools(), role="epic_manager")
    captured: dict[str, object] = {}

    async def fake_exec(*argv: object, **kwargs: object) -> _FakeProc:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _FakeProc(returncode=0, stdout=b"plan done")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = asyncio.run(run_claude_role(turn, token="sk-test"))
    assert result.status == "finished"
    assert result.text == "plan done"
    argv = captured["argv"]
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "--strict-mcp-config" in argv
    idx = argv.index("--mcp-config")
    mcp_path = argv[idx + 1]
    assert Path(str(mcp_path)).is_file()
    payload = json.loads(Path(str(mcp_path)).read_text(encoding="utf-8"))
    assert "mcpServers" in payload
    assert "cascade" in payload["mcpServers"]
    kwargs = captured["kwargs"]
    assert kwargs["cwd"] == os.fspath(cwd)
    assert kwargs["env"]["ANTHROPIC_API_KEY"] == "sk-test"
    assert captured["kwargs"]["stdin"] is asyncio.subprocess.PIPE


def test_planning_role_empty_tools_does_not_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cascade.agent.cli_common as cli_common

    cli_common._help_cache.clear()
    spawned = False

    async def fake_exec(*_argv: object, **_kwargs: object) -> _FakeProc:
        nonlocal spawned
        spawned = True
        return _FakeProc(returncode=0, stdout=b"no")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    turn = _turn(tools=[], role="epic_manager", cwd=Path("/tmp/plan-no-tools"))
    with pytest.raises(ProviderToolHostError, match="MCP tools"):
        asyncio.run(run_claude_role(turn, token="sk-test"))
    assert not spawned


def test_claude_mcp_missing_in_help_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def bare_help(_binary: str, *_prefix: str) -> str:
        return "Usage: claude -p --print only"

    import cascade.agent.cli_common as cli_common

    cli_common._help_cache.clear()
    monkeypatch.setattr("cascade.agent.claude_cli.read_cli_help", bare_help)
    turn = _turn(tools=_mcp_tools(), role="boss", cwd=Path("/tmp/claude-fail-closed"))
    with pytest.raises(ProviderToolHostError, match="mcp-config"):
        asyncio.run(run_claude_role(turn, token="sk-test"))


def test_codex_unsupported_mcp_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_help(binary: str, *prefix: str) -> str:
        if prefix == ("exec",):
            return "codex exec\n  --ask-for-approval never\n"
        return "no mcp here"

    import cascade.agent.cli_common as cli_common

    cli_common._help_cache.clear()
    monkeypatch.setattr("cascade.agent.codex_cli.read_cli_help", fake_help)
    turn = _turn(provider="codex", tools=_mcp_tools(), cwd=Path("/tmp/codex-fail"))
    with pytest.raises(ProviderToolHostError, match="MCP"):
        asyncio.run(run_codex_role(turn, token="sk-test"))


def test_codex_exec_with_mcp_uses_inline_config_and_preserves_codex_home(
    mock_help: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    turn = _turn(provider="codex", cwd=tmp_path, tools=_mcp_tools())
    captured: dict[str, object] = {}

    async def fake_exec(*argv: object, **kwargs: object) -> _FakeProc:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _FakeProc(returncode=0, stdout=b"ok")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(run_codex_role(turn, token="openai-key"))
    assert result.status == "finished"
    argv = captured["argv"]
    assert argv[:3] == ["codex", "exec", "--color"]
    assert argv[-1] == "-"
    env = captured["kwargs"]["env"]
    assert "CODEX_HOME" not in env
    assert "--ignore-user-config" in argv
    overrides = [argv[index + 1] for index, arg in enumerate(argv) if arg == "--config"]
    assert any(value.startswith("mcp_servers.cascade.command=") for value in overrides)
    assert 'mcp_servers.cascade.default_tools_approval_mode="approve"' in overrides
    assert "mcp_servers.cascade.required=true" in overrides
    assert any("CASCADE_MCP_CONFIG" in value for value in overrides)
    assert env["OPENAI_API_KEY"] == "openai-key"
    assert captured["kwargs"]["cwd"] == os.fspath(tmp_path)


def test_swe_turn_uses_worktree_cwd_in_argv_build() -> None:
    wt = Path("/data/worktrees/task_001")
    argv = build_claude_argv(
        _turn(cwd=wt, tools=[]),
        mcp_config_path=None,
        print_help=_CLAUDE_HELP,
    )
    assert "-p" in argv
    assert wt  # cwd enforced at subprocess layer; argv has no cwd


def test_reject_interactive_claude_argv() -> None:
    with pytest.raises(ProviderCliError, match="interactive"):
        assert_claude_non_interactive(["claude", "chat"])
    with pytest.raises(ProviderCliError, match="interactive"):
        assert_codex_non_interactive(["codex"])


def test_build_codex_argv_requires_exec_subcommand() -> None:
    argv = build_codex_argv(_turn(provider="codex"), exec_help=_CODEX_EXEC_HELP)
    assert argv[1] == "exec"


def test_build_codex_argv_sets_approval_policy_via_exec_config() -> None:
    argv = build_codex_argv(_turn(provider="codex"), exec_help=_CODEX_EXEC_HELP)
    assert "--ask-for-approval" not in argv
    assert argv[argv.index("--config") + 1] == 'approval_policy="never"'


def test_build_codex_argv_enables_flex_service_tier_only_when_selected() -> None:
    enabled = build_codex_argv(
        _turn(provider="codex", flex_mode=True), exec_help=_CODEX_EXEC_HELP
    )
    disabled = build_codex_argv(
        _turn(provider="codex", flex_mode=False), exec_help=_CODEX_EXEC_HELP
    )
    legacy = build_codex_argv(_turn(provider="codex"), exec_help=_CODEX_EXEC_HELP)

    assert 'service_tier="flex"' in enabled
    assert 'service_tier="flex"' not in disabled
    assert 'service_tier="flex"' not in legacy

def test_build_codex_argv_applies_selected_reasoning_effort() -> None:
    turn = _turn(provider="codex", model_id="gpt-5.6-sol", reasoning_level="high")
    argv = build_codex_argv(turn, exec_help=_CODEX_EXEC_HELP)
    assert 'model_reasoning_effort="high"' in argv

    default_argv = build_codex_argv(
        _turn(provider="codex", model_id="gpt-5.6-sol"), exec_help=_CODEX_EXEC_HELP
    )
    assert not any("model_reasoning_effort=" in value for value in default_argv)


def test_build_codex_argv_allows_planning_scratch_directory() -> None:
    argv = build_codex_argv(_turn(provider="codex"), exec_help=_CODEX_EXEC_HELP)
    assert "--skip-git-repo-check" in argv
    assert argv[-1] == "-"


def test_nonzero_exit_is_role_result_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_exec(*_argv: object, **_kwargs: object) -> _FakeProc:
        return _FakeProc(returncode=2, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(
        run_subprocess_turn(
            argv=["claude", "-p", "-"],
            cwd=Path("/tmp"),
            prompt="x",
        )
    )
    assert result.status == "error"
    assert "boom" in result.text


def test_claude_argv_includes_documented_flags() -> None:
    mcp_file = "/tmp/mcp.json"
    argv = build_claude_argv(
        _turn(tools=_mcp_tools()),
        mcp_config_path=mcp_file,
        print_help=_CLAUDE_HELP,
    )
    assert argv == [
        "claude",
        "-p",
        "--output-format",
        "text",
        "--strict-mcp-config",
        "--mcp-config",
        mcp_file,
        "--model",
        "claude-sonnet-4-6",
        "-",
    ]
