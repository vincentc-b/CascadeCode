"""Pre-persistence admission for effective provider selections."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from cascade.agent.discovery.inventory import (
    ProviderInventoryResult,
    get_provider_inventory,
)
from cascade.agent.selection_preflight import (
    RuntimeSelection,
    SelectionPreflight,
    evaluate_work_selection,
)
from cascade.board.parse import render_doc
from cascade.board.types import WorkDoc, WorkMeta


class SelectionAdmissionError(ValueError):
    """A safe, structured refusal to persist a provider selection."""

    def __init__(self, preflight: SelectionPreflight) -> None:
        self.preflight = preflight
        self.selections = preflight.selections
        self.result = preflight.result
        super().__init__(
            preflight.result.message or "selected configuration is not supported"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "selections": self.selections.to_dict(),
            "result": self.result.to_dict(),
        }


def admit_work_selection(
    doc: WorkDoc | WorkMeta,
    *,
    root: Path,
    action: str,
    inventory: ProviderInventoryResult | None = None,
    expected_revision: str | None = None,
) -> SelectionPreflight:
    """Return the complete safe result or raise it without persisting ``doc``."""

    available = inventory or get_provider_inventory()
    # A candidate's SHA is the optimistic write token for the old content.
    # Its selection provenance must instead describe the proposed content.
    candidate = (
        replace(
            doc,
            sha=f"sha256:{hashlib.sha256(render_doc(doc).encode('utf-8')).hexdigest()}",
        )
        if isinstance(doc, WorkDoc)
        else doc
    )
    preflight = evaluate_work_selection(
        candidate,
        root=Path(root).resolve(),
        inventory=available,
        action=action,
    )
    observed_revision = doc.sha if isinstance(doc, WorkDoc) else None
    if expected_revision is not None and observed_revision != expected_revision:
        # Reuse the shared evaluator's stale-selection projection so callers
        # receive the same safe role batch as launch-time provenance drift.
        preflight = evaluate_work_selection(
            candidate,
            root=Path(root).resolve(),
            inventory=available,
            action=action,
            runtime_selections=(
                RuntimeSelection(
                    role=item.role,
                    provider="__stale__",
                    model_id="__stale__",
                )
                for item in preflight.selections.selections
            ),
        )
    if not preflight.result.supported:
        raise SelectionAdmissionError(preflight)
    return preflight


def selection_configuration_changed(
    current: WorkDoc | WorkMeta,
    proposed: WorkDoc | WorkMeta,
) -> bool:
    """Whether a write introduces or changes reviewed selection fields."""

    before = current.meta if isinstance(current, WorkDoc) else current
    after = proposed.meta if isinstance(proposed, WorkDoc) else proposed
    return (
        before.provider != after.provider
        or before.model != after.model
        or before.models != after.models
        or before.reasoning != after.reasoning
        or before.flex_mode != after.flex_mode
        or before.parent_rev != after.parent_rev
    )


__all__ = [
    "SelectionAdmissionError",
    "admit_work_selection",
    "selection_configuration_changed",
]
