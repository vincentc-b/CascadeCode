"""Shared Feature/Epic recovery boundary across provider launchers."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cascade.agent.adapter import run_role
from cascade.agent.errors import (
    ProviderBudgetRefusedError,
    ProviderNotAuthenticatedError,
    ProviderNotInstalledError,
    ProviderToolHostError,
)
from cascade.agent.providers import ProviderStatus
from cascade.agent.recovery_contract import (
    ProviderRecoveryLaunch,
    launch_from_reconciliation,
)
from cascade.agent.types import IncidentProviderTurn, RoleResult, RoleTurn
from cascade.task.action_recovery import ActionReconciliation, create_or_load_action
from cascade.task.incident_budget import bind_incident_budget, read_incident_budget
from cascade.review_validation import (
    reserve_review_validation,
    review_validation_environment,
    run_review_validation,
)
from tests.support import make_repo


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


def _incident_turn(tmp_path: Path, *, operation_id: str = "provider:1") -> IncidentProviderTurn:
    root = make_repo(tmp_path, git=False)
    action = create_or_load_action(
        "review:42",
        "review_publication",
        root=root,
        attempt_bound=3,
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "task_001"},
    )
    bind_incident_budget(
        "review:42",
        "review:42",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    return IncidentProviderTurn("review:42", "claim:owner", operation_id, root)


@pytest.mark.parametrize("provider", ["cursor", "claude", "codex"])
def test_every_provider_receives_one_recovery_identity_and_reports_one_contract(
    monkeypatch: pytest.MonkeyPatch, provider: str, tmp_path: Path
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
    incident_turn = _incident_turn(tmp_path)
    result = asyncio.run(
        run_role(
            RoleTurn(
                role="feature_lead",
                provider=provider,  # type: ignore[arg-type]
                model_id="model",
                prompt=recovery.prompt_block(),
                cwd=Path.cwd(),
                recovery=recovery,
                    incident_turn=incident_turn,
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
    assert result.invocation is not None
    assert result.invocation.provider == provider
    assert result.invocation.usage.input.quality == "unavailable"
    budget = read_incident_budget("review:42", root=incident_turn.root)
    assert budget is not None
    receipt = budget["operations"]["provider:1"]
    assert receipt["state"] == "settled"
    assert receipt["observation"]["invocation"]["model_id"] == "model"
    assert receipt["observation"]["invocation"]["usage"]["cached_input"] == {
        "quality": "unavailable",
        "value": None,
    }


def test_active_recovery_without_incident_budget_refuses_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = AsyncMock()
    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda provider: ProviderStatus(provider, True, True, "env"),
    )
    monkeypatch.setattr(
        "cascade.agent.adapter.resolve_credential", lambda _provider: _Credential()
    )
    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", dispatch)
    with pytest.raises(ProviderBudgetRefusedError, match="incident_budget_required"):
        asyncio.run(
            run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="codex",
                    model_id="model",
                    prompt="recover",
                    cwd=Path.cwd(),
                    recovery=_launch(),
                )
            )
        )
    dispatch.assert_not_awaited()


@pytest.mark.parametrize("refusal", ["missing_capability", "missing_credential"])
def test_provider_preflight_refusal_preserves_incident_without_transport_or_charge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, refusal: str
) -> None:
    bounded = _incident_turn(tmp_path)
    dispatch = AsyncMock()
    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", dispatch)
    if refusal == "missing_capability":
        monkeypatch.setattr(
            "cascade.agent.adapter.probe_provider",
            lambda provider: ProviderStatus(provider, False, False, "not installed"),
        )
        expected = ProviderNotInstalledError
    else:
        monkeypatch.setattr(
            "cascade.agent.adapter.probe_provider",
            lambda provider: ProviderStatus(provider, True, True, "env"),
        )
        monkeypatch.setattr(
            "cascade.agent.adapter.resolve_credential", lambda _provider: None
        )
        expected = ProviderNotAuthenticatedError

    with pytest.raises(expected):
        asyncio.run(
            run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="codex",
                    model_id="model",
                    prompt="recover",
                    cwd=Path.cwd(),
                    recovery=_launch(),
                    incident_turn=bounded,
                )
            )
        )

    dispatch.assert_not_awaited()
    budget = read_incident_budget(bounded.incident_id, root=bounded.root)
    assert budget is not None
    assert budget["incident_id"] == bounded.incident_id
    assert budget["policy"]["version"] == bounded.policy_version
    assert budget["operations"] == {}
    assert budget["charged"]["paid_turns"] == 0
    assert budget["charged"]["model_seconds"] == 0


def test_fake_transport_settles_once_and_provider_switch_cannot_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CASCADE_ENABLE_FAKE_PROVIDER", "1")
    incident_turn = _incident_turn(tmp_path)
    recovery = _launch()
    first = asyncio.run(
        run_role(
            RoleTurn(
                role="feature_lead",
                provider="fake",
                model_id="fast",
                prompt="recover",
                cwd=Path.cwd(),
                recovery=recovery,
                incident_turn=incident_turn,
            )
        )
    )
    assert first.status == "finished"
    assert first.invocation is not None
    assert first.invocation.provider == "fake"

    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda provider: ProviderStatus(provider, True, True, "env"),
    )
    monkeypatch.setattr(
        "cascade.agent.adapter.resolve_credential", lambda _provider: _Credential()
    )
    dispatch = AsyncMock()
    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", dispatch)
    with pytest.raises(ProviderBudgetRefusedError, match="operation_identity_replayed"):
        asyncio.run(
            run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="codex",
                    model_id="replacement",
                    prompt="recover",
                    cwd=Path.cwd(),
                    recovery=recovery,
                    incident_turn=incident_turn,
                )
            )
        )
    dispatch.assert_not_awaited()
    budget = read_incident_budget("review:42", root=incident_turn.root)
    assert budget is not None
    assert budget["charged"]["paid_turns"] == 1
    assert len(budget["operations"]) == 1


@pytest.mark.parametrize(
    "launch_route",
    [
        "direct",
        "manual",
        "periodic",
        "audit",
        "briefing",
        "provider_switch",
        "parent",
        "replacement_action",
    ],
)
def test_every_recovery_launch_route_is_attributed_to_one_physical_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    launch_route: str,
) -> None:
    """Every entry path reaches the same prelaunch reservation boundary."""

    bounded = _incident_turn(tmp_path)
    routed = IncidentProviderTurn(
        bounded.incident_id,
        bounded.claim_id,
        bounded.operation_id,
        bounded.root,
        launch_route=launch_route,  # type: ignore[arg-type]
    )
    monkeypatch.setenv("CASCADE_ENABLE_FAKE_PROVIDER", "1")
    physical_invocations: list[str] = []
    from cascade.agent import adapter

    real_dispatch = adapter._dispatch_role

    async def dispatch(turn: RoleTurn, **kwargs: object) -> RoleResult:
        physical_invocations.append(turn.model_id)
        return await real_dispatch(turn, **kwargs)

    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", dispatch)
    result = asyncio.run(
        run_role(
            RoleTurn(
                role="feature_lead",
                provider="fake",
                model_id="fast",
                prompt="recover",
                cwd=Path.cwd(),
                recovery=_launch(),
                incident_turn=routed,
            )
        )
    )

    assert result.status == "finished"
    assert physical_invocations == ["fast"]
    budget = read_incident_budget(routed.incident_id, root=routed.root)
    assert budget is not None
    receipt = budget["operations"][routed.operation_id]
    assert receipt["attributes"]["launch_route"] == launch_route
    assert receipt["charged"]["paid_turns"] == 1
    assert receipt["observation"]["provider_started"] is True


def test_route_provider_and_model_changes_cannot_replay_an_operation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cosmetic caller changes never turn a settled operation into allowance."""

    bounded = _incident_turn(tmp_path)
    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda provider: ProviderStatus(provider, True, True, "env"),
    )
    monkeypatch.setattr(
        "cascade.agent.adapter.resolve_credential", lambda _provider: _Credential()
    )
    physical_invocations: list[tuple[str, str]] = []

    async def dispatch(turn: RoleTurn, **kwargs: object) -> RoleResult:
        physical_invocations.append((str(kwargs["provider"]), turn.model_id))
        return RoleResult(text="done", status="finished")

    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", dispatch)
    asyncio.run(
        run_role(
            RoleTurn(
                role="feature_lead",
                provider="codex",
                model_id="original",
                prompt="recover",
                cwd=Path.cwd(),
                recovery=_launch(),
                incident_turn=bounded,
            )
        )
    )
    replay = IncidentProviderTurn(
        bounded.incident_id,
        bounded.claim_id,
        bounded.operation_id,
        bounded.root,
        launch_route="replacement_action",
    )
    with pytest.raises(ProviderBudgetRefusedError, match="operation_identity_replayed"):
        asyncio.run(
            run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="claude",
                    model_id="replacement",
                    prompt="cosmetically revised recovery prompt",
                    cwd=Path.cwd(),
                    recovery=_launch(),
                    incident_turn=replay,
                )
            )
        )

    assert physical_invocations == [("codex", "original")]
    budget = read_incident_budget(bounded.incident_id, root=bounded.root)
    assert budget is not None
    assert budget["charged"]["paid_turns"] == 1
    assert len(budget["operations"]) == 1


def test_unknown_recovery_launch_route_fails_before_admission(tmp_path: Path) -> None:
    bounded = _incident_turn(tmp_path)
    with pytest.raises(ValueError, match="unsupported recovery launch route"):
        IncidentProviderTurn(
            bounded.incident_id,
            bounded.claim_id,
            bounded.operation_id,
            bounded.root,
            launch_route="dashboard_retry",  # type: ignore[arg-type]
        )


def test_model_runtime_bound_above_trusted_maximum_refuses_before_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CASCADE_ENABLE_FAKE_PROVIDER", "1")
    bounded = _incident_turn(tmp_path)
    invalid = IncidentProviderTurn(
        bounded.incident_id,
        bounded.claim_id,
        bounded.operation_id,
        bounded.root,
        worst_case_model_seconds=901,
    )
    with pytest.raises(ProviderBudgetRefusedError, match="model_runtime_bound_exceeds_policy"):
        asyncio.run(
            run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="fake",
                    model_id="fast",
                    prompt="recover",
                    cwd=Path.cwd(),
                    recovery=_launch(),
                    incident_turn=invalid,
                )
            )
        )
    budget = read_incident_budget("review:42", root=bounded.root)
    assert budget is not None
    assert budget["operations"] == {}


def test_adapter_prelaunch_failure_releases_reservation_without_paid_charge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bounded = _incident_turn(tmp_path)
    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda provider: ProviderStatus(provider, True, True, "env"),
    )
    monkeypatch.setattr(
        "cascade.agent.adapter.resolve_credential", lambda _provider: _Credential()
    )

    async def fail_before_start(*_args: object, **_kwargs: object) -> RoleResult:
        raise ProviderToolHostError("no guarded transport")

    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", fail_before_start)
    with pytest.raises(ProviderToolHostError):
        asyncio.run(
            run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="codex",
                    model_id="model",
                    prompt="recover",
                    cwd=Path.cwd(),
                    recovery=_launch(),
                    incident_turn=bounded,
                )
            )
        )
    budget = read_incident_budget("review:42", root=bounded.root)
    assert budget is not None
    receipt = budget["operations"]["provider:1"]
    assert receipt["observation"]["provider_started"] is False
    assert receipt["charged"]["paid_turns"] == 0
    assert receipt["charged"]["model_seconds"] == 0


def test_fake_transport_interruption_retains_worst_case_and_blocks_competitor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CASCADE_ENABLE_FAKE_PROVIDER", "1")
    first_turn = _incident_turn(tmp_path, operation_id="provider:running")
    second_turn = IncidentProviderTurn(
        first_turn.incident_id,
        first_turn.claim_id,
        "provider:competing",
        first_turn.root,
    )

    async def exercise() -> None:
        running = asyncio.create_task(
            run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="fake",
                    model_id="forever-connected",
                    prompt="recover",
                    cwd=Path.cwd(),
                    recovery=_launch(),
                    incident_turn=first_turn,
                )
            )
        )
        for _ in range(100):
            budget = read_incident_budget("review:42", root=first_turn.root)
            if budget and "provider:running" in budget["operations"]:
                break
            await asyncio.sleep(0.01)
        with pytest.raises(ProviderBudgetRefusedError, match="serialized_operation_in_flight"):
            await run_role(
                RoleTurn(
                    role="feature_lead",
                    provider="fake",
                    model_id="fast",
                    prompt="recover",
                    cwd=Path.cwd(),
                    recovery=_launch(),
                    incident_turn=second_turn,
                )
            )
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(exercise())
    budget = read_incident_budget("review:42", root=first_turn.root)
    assert budget is not None
    assert budget["charged"]["paid_turns"] == 1
    assert budget["charged"]["model_seconds"] == 300
    assert budget["consumption_quality"] == "unavailable"
    assert budget["wait_reason"] == "in_flight_usage_reconciliation_required"


def test_provider_can_run_one_linked_real_validator_while_competitor_waits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bounded = _incident_turn(tmp_path, operation_id="provider:owner")
    monkeypatch.setattr(
        "cascade.agent.adapter.probe_provider",
        lambda provider: ProviderStatus(provider, True, True, "env"),
    )
    monkeypatch.setattr(
        "cascade.agent.adapter.resolve_credential", lambda _provider: _Credential()
    )

    async def dispatch(_turn: RoleTurn, **_kwargs: object) -> RoleResult:
        decision, operation = reserve_review_validation(
            bounded.incident_id,
            bounded.claim_id,
            "validator:provider-child",
            root=bounded.root,
            timeout=5,
            environment_revision=review_validation_environment(),
            parent_operation_id=bounded.operation_id,
        )
        assert decision.admitted
        assert operation is not None
        competing, _ = reserve_review_validation(
            bounded.incident_id,
            bounded.claim_id,
            "validator:competing",
            root=bounded.root,
            timeout=5,
            environment_revision=review_validation_environment(),
        )
        assert competing.reason == "serialized_operation_in_flight"
        result = run_review_validation(
            (sys.executable, "-c", "print('validated')"),
            cwd=bounded.root,
            timeout=5,
            operation=operation,
        )
        assert result.returncode == 0
        return RoleResult(text="done", status="finished")

    monkeypatch.setattr("cascade.agent.adapter._dispatch_role", dispatch)
    result = asyncio.run(
        run_role(
            RoleTurn(
                role="feature_lead",
                provider="codex",
                model_id="model",
                prompt="recover",
                cwd=Path.cwd(),
                recovery=_launch(),
                incident_turn=bounded,
            )
        )
    )
    assert result.status == "finished"
    budget = read_incident_budget(bounded.incident_id, root=bounded.root)
    assert budget is not None
    assert budget["operations"]["provider:owner"]["state"] == "settled"
    child = budget["operations"]["validator:provider-child"]
    assert child["state"] == "settled"
    assert child["attributes"]["parent_operation_id"] == "provider:owner"
    assert "validator:competing" not in budget["operations"]
    assert budget["charged"]["paid_turns"] == 1
    assert budget["charged"]["model_seconds"] == 300
    assert budget["charged"]["tool_attempts"] == 1


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
