"""Atomic provider-pin recovery for an active work item.

This module deliberately has no knowledge of board documents, worktrees, or
LangGraph.  The lifecycle owns those resources and supplies two tiny durable
stores: one for the user-visible selection and one for checkpoint pins.  That
keeps this transaction useful for all three work tiers while ensuring that a
failed second write is compensated before a caller can start another turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Protocol

from cascade.agent.discovery.inventory import ProviderInventoryResult, refresh_provider_inventory
from cascade.agent.preflight import ProviderCapabilityPreflight, preflight_provider_capability
from cascade.agent.providers import ProviderId

RecoveryDisposition = Literal["resume_compatible", "fresh_role_turn"]

_ROLES: dict[str, tuple[str, ...]] = {
    "epic": ("epic_manager", "epic_architect"),
    "feature": ("feature_lead", "feature_architect"),
    "task": ("swe",),
}


@dataclass(frozen=True)
class ActiveRoleSelection:
    """The complete persisted backend selection for one direct role."""

    provider: ProviderId
    model_id: str
    reasoning_level: str | None = None
    flex_mode: bool | None = None


class RecoveryStore(Protocol):
    """Durable role-pin store used by :func:`recover_active_provider_pins`.

    ``write`` must replace pins for the active item only.  It must not merge
    selections belonging to children: the recovery engine never reads or
    writes children and callers should scope their store accordingly.
    """

    def read(self) -> Mapping[str, ActiveRoleSelection]: ...

    def write(self, pins: Mapping[str, ActiveRoleSelection]) -> None: ...


@dataclass(frozen=True)
class ProviderRecoveryResult:
    """Safe next action after a provider selection recovery."""

    disposition: RecoveryDisposition
    compatible_checkpoint: bool
    checks: tuple[ProviderCapabilityPreflight, ...]

    @property
    def resume_existing_state(self) -> bool:
        """Whether opaque checkpoint turn state is proven safe to resume."""

        return self.disposition == "resume_compatible"


class ProviderRecoveryValidationError(ValueError):
    """The requested selection is incomplete or unsupported; nothing changed."""


class ProviderRecoveryTransactionError(RuntimeError):
    """A persistence write failed after rollback was attempted."""


def roles_for_tier(tier: str) -> tuple[str, ...]:
    """Return exactly the roles owned by an active item at ``tier``."""

    try:
        return _ROLES[tier]
    except KeyError as exc:
        raise ProviderRecoveryValidationError(f"unknown work tier {tier!r}") from exc


def recover_active_provider_pins(
    *,
    tier: str,
    selections: Mapping[str, ActiveRoleSelection],
    selection_store: RecoveryStore,
    checkpoint_store: RecoveryStore,
    inventory: ProviderInventoryResult | None = None,
    inventory_loader: Callable[[], ProviderInventoryResult] = refresh_provider_inventory,
) -> ProviderRecoveryResult:
    """Validate and atomically reconcile persisted selection and checkpoint pins.

    Every direct role is checked before either store is changed.  The old
    values are then restored if either write fails.  Compatibility is strict:
    a checkpoint can only resume when *all* existing pins equal the requested
    complete selection.  Any provider/model/reasoning/flex change therefore
    produces ``fresh_role_turn`` rather than reusing opaque provider state.
    """

    expected_roles = roles_for_tier(tier)
    proposed = _complete_selection(expected_roles, selections)
    available = inventory if inventory is not None else inventory_loader()
    checks = tuple(
        preflight_provider_capability(
            provider=proposed[role].provider,
            model_id=proposed[role].model_id,
            tier=tier,
            inventory=available,
            reasoning_level=proposed[role].reasoning_level,
            flex_mode=proposed[role].flex_mode,
        )
        for role in expected_roles
    )
    failures = [check for check in checks if not check.supported]
    if failures:
        reasons = ", ".join(f"{role}: {check.reason}" for role, check in zip(expected_roles, checks) if not check.supported)
        raise ProviderRecoveryValidationError(f"provider recovery selection is unsupported ({reasons})")

    old_selection = dict(selection_store.read())
    old_checkpoint = dict(checkpoint_store.read())
    compatible = _same_pins(old_checkpoint, proposed, expected_roles)

    # Do not special-case a no-op before validation: an idempotent retry still
    # proves current provider capability and repairs a stale persisted side.
    selection_written = False
    checkpoint_written = False
    try:
        selection_store.write(proposed)
        selection_written = True
        checkpoint_store.write(proposed)
        checkpoint_written = True
    except Exception as exc:
        rollback_errors: list[BaseException] = []
        # Restore both snapshots even if the failing writer may have partially
        # applied data.  This makes writers that fail after fsync safe too.
        for store, snapshot, touched in (
            (checkpoint_store, old_checkpoint, checkpoint_written or True),
            (selection_store, old_selection, selection_written or True),
        ):
            if not touched:
                continue
            try:
                store.write(snapshot)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic store failure
                rollback_errors.append(rollback_exc)
        detail = "provider recovery transaction failed; prior pins restored"
        if rollback_errors:
            detail += "; rollback failed"
        raise ProviderRecoveryTransactionError(detail) from exc

    return ProviderRecoveryResult(
        disposition="resume_compatible" if compatible else "fresh_role_turn",
        compatible_checkpoint=compatible,
        checks=checks,
    )


def _complete_selection(
    expected_roles: tuple[str, ...], selections: Mapping[str, ActiveRoleSelection]
) -> dict[str, ActiveRoleSelection]:
    actual = set(selections)
    expected = set(expected_roles)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail = []
        if missing:
            detail.append("missing roles: " + ", ".join(missing))
        if extra:
            detail.append("unexpected roles: " + ", ".join(extra))
        raise ProviderRecoveryValidationError("incomplete active-item selection (" + "; ".join(detail) + ")")
    return {role: selections[role] for role in expected_roles}


def _same_pins(
    current: Mapping[str, ActiveRoleSelection],
    proposed: Mapping[str, ActiveRoleSelection],
    expected_roles: tuple[str, ...],
) -> bool:
    return set(current) == set(expected_roles) and all(current[role] == proposed[role] for role in expected_roles)


__all__ = [
    "ActiveRoleSelection",
    "ProviderRecoveryResult",
    "ProviderRecoveryTransactionError",
    "ProviderRecoveryValidationError",
    "RecoveryStore",
    "recover_active_provider_pins",
    "roles_for_tier",
]
