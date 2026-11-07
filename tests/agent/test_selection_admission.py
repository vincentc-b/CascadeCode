"""Pre-persistence selection admission keeps safe role-level refusals."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.agent.selection_admission import (
    SelectionAdmissionError,
    admit_work_selection,
)
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc
from tests.support import add_doc, make_repo


def _inventory(*models: str) -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=tuple(DiscoveredModel(id=value, display_name=value) for value in models),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )


def _task(root: Path, model: str) -> WorkDoc:
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    doc = read_doc("task_001", root=root)
    doc.meta.provider = "codex"
    doc.meta.models = {"swe": model}
    return doc


def test_task_admission_rejects_invalid_swe_with_structured_result(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    doc = _task(root, "future-model")

    with pytest.raises(SelectionAdmissionError) as caught:
        admit_work_selection(
            doc,
            root=root,
            inventory=_inventory("offered-model"),
            action="task_configuration_write",
        )

    assert caught.value.result.reason_code == "model_not_offered"
    assert caught.value.result.affected_roles == ("swe",)
    assert caught.value.selections.work_id == "task_001"
    assert caught.value.to_dict()["result"]["checks"][0]["role"] == "swe"
    assert "future-model" not in doc.meta.path.read_text(encoding="utf-8")


def test_admission_rejects_transient_inventory_without_persisting(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    doc = _task(root, "offered-model")
    unavailable = ProviderInventoryResult(
        providers=(),
        failures=(
            ProviderInventoryFailure(
                provider_id="codex",
                reason="not_authenticated",
                message="safe",
                failure_kind="provider_not_authenticated",
            ),
        ),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )

    with pytest.raises(SelectionAdmissionError) as caught:
        admit_work_selection(
            doc,
            root=root,
            inventory=unavailable,
            action="task_configuration_write",
        )

    assert caught.value.result.outcome == "transient"
    assert caught.value.result.reason_code == "provider_not_authenticated"


def test_admission_marks_stale_document_provenance(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    doc = _task(root, "offered-model")
    write_doc(doc, root=root)
    stale = read_doc("task_001", root=root)
    current = read_doc("task_001", root=root)
    current.body += "\nnew revision\n"
    write_doc(current, root=root)

    with pytest.raises(SelectionAdmissionError) as caught:
        admit_work_selection(
            stale,
            root=root,
            inventory=_inventory("offered-model"),
            action="task_configuration_write",
            expected_revision=current.sha,
        )

    assert caught.value.result.reason_code == "stale_selection"
    assert caught.value.result.affected_roles == ("swe",)
