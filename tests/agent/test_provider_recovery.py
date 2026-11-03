from __future__ import annotations

import pytest

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.agent.provider_recovery import (
    ActiveRoleSelection,
    ProviderRecoveryTransactionError,
    ProviderRecoveryValidationError,
    recover_active_provider_pins,
)


class Store:
    def __init__(self, pins, *, fail=False):
        self.pins = dict(pins)
        self.fail = fail
        self.writes = []

    def read(self):
        return dict(self.pins)

    def write(self, pins):
        self.writes.append(dict(pins))
        self.pins = dict(pins)  # model a failure after an underlying write
        if self.fail:
            self.fail = False
            raise OSError("disk full")


def _inventory() -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex", display_name="Codex",
                models=(DiscoveredModel(id="gpt-5", display_name="GPT-5"),),
                supports_flex_mode=True,
            ),
        ),
        failures=(), freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )


def _selection(model="gpt-5"):
    return {"swe": ActiveRoleSelection("codex", model, flex_mode=True)}


def test_invalid_role_selection_does_not_mutate_either_store():
    selected = Store(_selection())
    checkpoint = Store(_selection())

    with pytest.raises(ProviderRecoveryValidationError, match="missing roles"):
        recover_active_provider_pins(
            tier="feature", selections={"feature_lead": _selection()["swe"]},
            selection_store=selected, checkpoint_store=checkpoint, inventory=_inventory()
        )

    assert selected.writes == []
    assert checkpoint.writes == []


def test_unsupported_selection_does_not_mutate_either_store():
    original = _selection()
    selected = Store(original)
    checkpoint = Store(original)

    with pytest.raises(ProviderRecoveryValidationError, match="model_not_offered"):
        recover_active_provider_pins(
            tier="task", selections=_selection("missing"), selection_store=selected,
            checkpoint_store=checkpoint, inventory=_inventory()
        )

    assert selected.pins == original
    assert checkpoint.pins == original


def test_second_write_failure_rolls_back_both_persistence_targets():
    old = {"swe": ActiveRoleSelection("codex", "gpt-5")}
    selected = Store(old)
    checkpoint = Store(old, fail=True)
    new = _selection()

    with pytest.raises(ProviderRecoveryTransactionError, match="prior pins restored"):
        recover_active_provider_pins(
            tier="task", selections=new, selection_store=selected,
            checkpoint_store=checkpoint, inventory=_inventory()
        )

    assert selected.pins == old
    assert checkpoint.pins == old


def test_only_exact_full_checkpoint_pins_can_resume():
    selection = _selection()
    result = recover_active_provider_pins(
        tier="task", selections=selection, selection_store=Store(selection),
        checkpoint_store=Store(selection), inventory=_inventory()
    )
    assert result.disposition == "resume_compatible"

    changed = recover_active_provider_pins(
        tier="task", selections=selection,
        selection_store=Store({"swe": ActiveRoleSelection("codex", "gpt-5")}),
        checkpoint_store=Store({"swe": ActiveRoleSelection("codex", "gpt-5")}),
        inventory=_inventory(),
    )
    assert changed.disposition == "fresh_role_turn"
