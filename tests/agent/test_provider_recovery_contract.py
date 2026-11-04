"""Shared Feature/Epic recovery boundary across provider launchers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from cascade.agent.adapter import run_role
from cascade.agent.providers import ProviderStatus
from cascade.agent.recovery_contract import (
    ProviderRecoveryLaunch,
    launch_from_reconciliation,
)
from cascade.agent.types import RoleResult, RoleTurn
from cascade.task.action_recovery import ActionReconciliation


def _launch(outcome: str = "resume") -> ProviderRecoveryLaunch:
    return ProviderRecoveryLaunch(
        action_id="review:42",
        checkpoint_id="rebase:checkpoint",
        outcome=outcome,  # type: ignore[arg-type]
        evidence={
            "refs": {"source": "topic", "target": "main"},
            "shas": {"source_head": "a", "target_head": "b"},
            "affected_paths": ["cascade/agent/adapter.py"],
            "command_summary": "git rebase origin/main",
            "test_summary": "not run",
            "resume_instructions": "Resume with this action identity.",
        },
    )


@dataclass(frozen=True)
class _Credential:
    token: str = "token"


@pytest.mark.parametrize("provider", ["cursor", "claude", "codex"])
def test_every_provider_receives_one_recovery_identity_and_reports_one_contract(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    launched: list[RoleTurn] = []

    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda _provider: ProviderStatus(_provider, True, True, "env"),
    )
    monkeypatch.setattr("cascade.agent.adapter.resolve_credential", lambda _provider: _Credential())

    async def dispatch(turn: RoleTurn, **_kwargs: object) -> RoleResult:
        launched.append(turn)
        return RoleResult(text="done", status="finished")

    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", dispatch)
    recovery = _launch()
    result = asyncio.run(
        run_role(
            RoleTurn(
                role="feature_lead",
                provider=provider,  # type: ignore[arg-type]
                model_id="model",
                prompt=recovery.prompt_block(),
                cwd=Path.cwd(),
                recovery=recovery,
            )
        )
    )

    assert len(launched) == 1
    assert launched[0].recovery == recovery
    assert result.recovery is not None
    assert result.recovery.action_id == "review:42"
    assert result.recovery.checkpoint_id == "rebase:checkpoint"
    assert result.recovery.outcome == "completed"
    assert result.recovery.evidence["provider"] == provider


@pytest.mark.parametrize("outcome, expected_status", [("completed", "finished"), ("blocked", "error")])
def test_terminal_recovery_is_reported_without_relaunching_provider(
    monkeypatch: pytest.MonkeyPatch, outcome: str, expected_status: str,
) -> None:
    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda _provider: ProviderStatus(_provider, True, True, "env"),
    )
    monkeypatch.setattr("cascade.agent.adapter.resolve_credential", lambda _provider: _Credential())

    async def must_not_dispatch(*_args: object, **_kwargs: object) -> RoleResult:
        raise AssertionError("a terminal recovery must not repeat provider effects")

    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", must_not_dispatch)
    result = asyncio.run(
        run_role(
            RoleTurn(
                role="epic_manager",
                provider="codex",
                model_id="model",
                prompt="ignored",
                cwd=Path.cwd(),
            recovery=_launch(outcome),
            )
        )
    )
    assert result.status == expected_status
    assert result.recovery is not None
    assert result.recovery.outcome == outcome
    assert result.recovery.evidence["provider_status"] == "not_launched"


def test_durable_reconciliation_uses_the_shared_provider_vocabulary() -> None:
    reconciliation = ActionReconciliation(
        "safe_retry", "source_head_unchanged", "review:42", "rebase:checkpoint", "a", "b",
        ("source.py",), "resume safely",
    )
    launch = launch_from_reconciliation(reconciliation, evidence={"refs": {"source": "topic"}})
    assert launch.outcome == "safe_retry"
    assert launch.evidence["affected_paths"] == ["source.py"]
    assert launch.evidence["resume_instructions"] == "resume safely"
