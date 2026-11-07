"""Scoped persistence and propagation for runtime-only Flex waivers."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from cascade.agent.flex_continuation_contract import (
    FlexWaiver,
    InventoryFreshnessAudit,
    WaiverScopeMember,
)
from cascade.board.types import WorkDoc
from cascade.provider_recovery_waiver import (
    persist_flex_waiver,
    stamp_minted_descendant_waivers,
)
from cascade.watchdog.model_resolve import (
    resolve_effective_selections,
    selection_member_fingerprint,
)
from tests.support import add_doc, make_repo


def _write_config(root: Path) -> None:
    (root / "cascade.toml").write_text(
        """
[providers]
default = "codex"

[providers.codex]
epic = "epic-model"
feature = "feature-model"
task = "task-model"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _doc(root: Path, *, work_id: str, tier: str, parent: str | None = None) -> WorkDoc:
    seed = add_doc(root, id="epic_999", title="Waiver", tier="epic")
    return WorkDoc(
        meta=replace(
            seed.meta,
            id=work_id,
            tier=tier,  # type: ignore[arg-type]
            parent=parent,
            path=root / "docs" / f"{tier}s" / "2_active" / f"{work_id}_waiver.md",
            provider="codex",
            model=None,
            models=None,
            reasoning=None,
            flex_mode=True,
        ),
        body=seed.body,
        sha=f"{work_id}-revision-1",
    )


def _authorize(batch, *, role: str, root: Path) -> FlexWaiver:
    selection = next(item for item in batch.selections if item.role == role)
    waiver = FlexWaiver(
        waiver_id="waiver-1",
        receipt_id="receipt-1",
        scope=(
            WaiverScopeMember(
                work_id=selection.work_id,
                role=selection.role,
                document_revision=selection.document_revision,
                selection_member_fingerprint=selection_member_fingerprint(selection),
            ),
        ),
        authorized_subject="human:operator",
        authorized_at="2026-11-07T12:00:00+00:00",
        inventory_freshness=InventoryFreshnessAudit(
            fetched_at=10.0,
            expires_at=70.0,
            age_seconds=1.0,
            stale=False,
            source_version="inventory-v1",
        ),
    )
    persist_flex_waiver(waiver, root=root)
    return waiver


def test_direct_waiver_is_runtime_only_and_revision_bound(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _write_config(root)
    doc = _doc(root, work_id="task_001", tier="task", parent="feat_001")
    reviewed = resolve_effective_selections(doc, root=root)
    ledger_path = root / ".cascade" / "provider_recoveries.json"
    ledger_path.write_text(
        json.dumps({"version": 1, "recoveries": {"legacy": {"reason": "kept"}}}),
        encoding="utf-8",
    )
    waiver = _authorize(reviewed, role="swe", root=root)

    effective = resolve_effective_selections(doc, root=root)
    selection = effective.selections[0]
    assert selection.reviewed_flex_mode is True
    assert selection.effective_flex_mode is False
    assert selection.flex_waiver_id == waiver.waiver_id
    assert selection.flex_waiver_receipt_id == waiver.receipt_id
    assert effective.selection_fingerprint == reviewed.selection_fingerprint

    revised = replace(doc, sha="task_001-revision-2")
    stale = resolve_effective_selections(revised, root=root).selections[0]
    assert stale.effective_flex_mode is True
    assert stale.flex_waiver_id is None

    raw = (root / ".cascade" / "provider_recoveries.json").read_text()
    assert "human:operator" in raw
    assert '"legacy"' in raw
    assert not any(secret in raw for secret in ("credential", "token", "provider_payload"))


def test_normal_descendant_stamp_carries_provenance_but_edit_invalidates(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _write_config(root)
    parent = _doc(root, work_id="feat_001", tier="feature", parent="epic_001")
    parent = replace(
        parent,
        meta=replace(parent.meta, models={"swe": "task-model"}),
    )
    parent_reviewed = resolve_effective_selections(parent, root=root)
    _authorize(parent_reviewed, role="swe", root=root)
    parent_effective = resolve_effective_selections(parent, root=root)

    child = _doc(root, work_id="task_001", tier="task", parent="feat_001")
    child = replace(child, meta=replace(child.meta, models={"swe": "task-model"}))
    child_reviewed = resolve_effective_selections(child, root=root)
    stamps = stamp_minted_descendant_waivers(
        parent_effective,
        child_reviewed,
        role_mapping={"swe": "swe"},
        root=root,
    )
    assert len(stamps) == 1

    inherited = resolve_effective_selections(child, root=root).selections[0]
    assert inherited.effective_flex_mode is False
    assert inherited.flex_waiver_id == "waiver-1"
    assert inherited.flex_waiver_source_work_id == "feat_001"

    edited = replace(child, sha="task_001-revision-2")
    invalidated = resolve_effective_selections(edited, root=root).selections[0]
    assert invalidated.effective_flex_mode is True
    assert invalidated.flex_waiver_id is None

    ledger = json.loads(
        (root / ".cascade" / "provider_recoveries.json").read_text(encoding="utf-8")
    )
    assert set(ledger) >= {"version", "flex_waivers", "flex_waiver_stamps"}
