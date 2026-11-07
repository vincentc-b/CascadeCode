"""Approval admission for effective downstream provider selections."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.agent.selection_admission import SelectionAdmissionError
from cascade.agent.selection_preflight import evaluate_work_selection
from cascade.approvals import ApprovalSelectionError, approve_epic_plan, approve_feature
from cascade.board.parse import parse_doc
from cascade.board.store import read_doc, write_doc
from cascade.war_room.server import WarRoomRequestHandler
from tests.support import add_doc, make_repo, sign_off_both_planning_roles


def _inventory(*models: str) -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=tuple(
                    DiscoveredModel(id=model, display_name=model) for model in models
                ),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )


def _select_feature(root: Path, feature_id: str, **overrides: str) -> None:
    doc = read_doc(feature_id, root=root)
    doc.meta.provider = "codex"
    doc.meta.models = {
        "feature_lead": "offered",
        "feature_architect": "offered",
        "swe": "offered",
        **overrides,
    }
    write_doc(doc, root=root)


def test_feature_approval_rejects_invalid_late_override_before_timestamp(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_feature(root, "feat_001", swe="future-model")

    with pytest.raises(ApprovalSelectionError) as caught:
        approve_feature("feat_001", root=root, inventory=_inventory("offered"))

    assert read_doc("feat_001", root=root).meta.approved_at is None
    assert caught.value.preflight.affected_roles == ("swe",)
    assert tuple(check.role for check in caught.value.preflight.checks) == (
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert caught.value.selections.roles[-1].document_path.endswith("feat_001_feature.md")


def test_feature_approval_preflights_existing_tasks_before_timestamp(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _select_feature(root, "feat_001")
    task = read_doc("task_001", root=root)
    task.meta.provider = "codex"
    task.meta.models = {"swe": "future-model"}
    write_doc(task, root=root)

    with pytest.raises(ApprovalSelectionError) as caught:
        approve_feature("feat_001", root=root, inventory=_inventory("offered"))

    assert [item.result.work_id for item in caught.value.preflights] == [
        "feat_001",
        "task_001",
    ]
    assert caught.value.preflight.affected_roles == ("swe",)
    assert read_doc("feat_001", root=root).meta.approved_at is None


def test_feature_approval_rejects_selection_changed_after_board_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_feature(root, "feat_001")

    def changed_document(path: Path):
        doc = parse_doc(path)
        doc.meta.models["swe"] = "changed-after-snapshot"
        return doc

    monkeypatch.setattr("cascade.approvals.parse_doc", changed_document)

    with pytest.raises(ApprovalSelectionError) as caught:
        approve_feature("feat_001", root=root, inventory=_inventory("offered"))

    assert caught.value.preflight.reason_code == "stale_selection"
    assert read_doc("feat_001", root=root).meta.approved_at is None


def test_feature_approval_projects_owning_document_loss_as_stale_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_feature(root, "feat_001")

    def lose_document(_path: Path):
        raise OSError("unsafe raw detail")

    monkeypatch.setattr("cascade.approvals.parse_doc", lose_document)

    with pytest.raises(ApprovalSelectionError) as caught:
        approve_feature("feat_001", root=root, inventory=_inventory("offered"))

    assert caught.value.preflight.reason_code == "stale_selection"
    assert "unsafe raw detail" not in str(caught.value)
    assert read_doc("feat_001", root=root).meta.approved_at is None


def test_feature_approval_fails_closed_for_unresolved_legacy_selection(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Legacy", tier="feature", parent="epic_001")

    with pytest.raises(ApprovalSelectionError) as caught:
        approve_feature("feat_001", root=root, inventory=_inventory("offered"))

    assert caught.value.preflight.reason_code == "missing_configuration"
    assert caught.value.preflight.affected_roles == (
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert read_doc("feat_001", root=root).meta.approved_at is None


def test_epic_approval_preflights_all_children_before_first_write(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="One", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Two", tier="feature", parent="epic_001")
    _select_feature(root, "feat_001", feature_lead="future-lead")
    _select_feature(root, "feat_002", swe="future-swe")
    sign_off_both_planning_roles("epic_001", root=root)

    with pytest.raises(ApprovalSelectionError) as caught:
        approve_epic_plan("epic_001", root=root, inventory=_inventory("offered"))

    assert [item.result.work_id for item in caught.value.failures] == [
        "feat_001",
        "feat_002",
    ]
    assert read_doc("feat_001", root=root).meta.approved_at is None
    assert read_doc("feat_002", root=root).meta.approved_at is None
    assert read_doc("epic_001", root=root).meta.plan_approved_at is None


def test_epic_approval_preflights_existing_tasks_before_first_write(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _select_feature(root, "feat_001")
    task = read_doc("task_001", root=root)
    task.meta.provider = "codex"
    task.meta.models = {"swe": "future-model"}
    write_doc(task, root=root)
    sign_off_both_planning_roles("epic_001", root=root)

    with pytest.raises(ApprovalSelectionError) as caught:
        approve_epic_plan("epic_001", root=root, inventory=_inventory("offered"))

    assert [item.result.work_id for item in caught.value.preflights] == [
        "feat_001",
        "task_001",
    ]
    assert read_doc("feat_001", root=root).meta.approved_at is None
    assert read_doc("epic_001", root=root).meta.plan_approved_at is None


def test_accepted_approval_survives_drift_and_reports_reconciliation_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_feature(root, "feat_001")
    available = _inventory("offered")
    approve_feature("feat_001", root=root, inventory=available)
    approved_at = read_doc("feat_001", root=root).meta.approved_at

    _select_feature(root, "feat_001", swe="future-model")
    drift = evaluate_work_selection(
        read_doc("feat_001", root=root),
        root=root,
        inventory=available,
        action="feature_dispatch",
    )
    refusal = SelectionAdmissionError(drift)
    monkeypatch.setattr(
        "cascade.watchdog.config.read_automation_config",
        lambda _root: SimpleNamespace(enabled=True),
    )

    def reject_dispatch(_root: Path, **_kwargs: object) -> None:
        raise refusal

    monkeypatch.setattr(
        "cascade.automation.reconcile_approval_dispatch", reject_dispatch
    )

    result = approve_feature("feat_001", root=root, inventory=available)

    assert result["newly_approved"] is False
    assert result["dispatch_pending"] is True
    assert result["preflight"]["reason_code"] == "model_not_offered"  # type: ignore[index]
    assert read_doc("feat_001", root=root).meta.approved_at == approved_at


def test_approval_reports_dispatch_refusal_returned_by_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_feature(root, "feat_001")
    available = _inventory("offered")
    approve_feature("feat_001", root=root, inventory=available)
    approved_at = read_doc("feat_001", root=root).meta.approved_at

    _select_feature(root, "feat_001", swe="future-model")
    root.joinpath("cascade.toml").write_text("[automation]\nenabled = true\n")
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: available
    )

    result = approve_feature("feat_001", root=root, inventory=available)

    assert result["newly_approved"] is False
    assert result["dispatch_pending"] is True
    assert [
        item["role"]
        for item in result["preflight"]["checks"]  # type: ignore[index]
        if item["outcome"] != "supported"
    ] == ["swe"]
    refusals = result["dispatch_refusals"]
    assert [item["work_id"] for item in refusals] == ["feat_001"]  # type: ignore[union-attr]
    assert refusals[0]["preflight"] == result["preflight"]  # type: ignore[index]
    assert read_doc("feat_001", root=root).meta.approved_at == approved_at


class _Handler:
    def __init__(self, root: Path) -> None:
        self.server = type("Server", (), {"root": root})()
        self.responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def _require_work_id(self, body: dict[str, object]) -> str | None:
        value = body.get("id")
        return value if isinstance(value, str) else None

    def _json_response(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.responses.append((status, payload))

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        self._json_response(status, {"error": message})


def test_feature_approval_route_preserves_structured_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_feature(root, "feat_001", feature_architect="future-model")
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: _inventory("offered"))
    handler = _Handler(root)

    WarRoomRequestHandler._handle_approve_feature(  # type: ignore[arg-type]
        handler, {"id": "feat_001"}
    )

    status, payload = handler.responses[0]
    assert status == HTTPStatus.CONFLICT
    assert payload["preflight"]["reason_code"] == "model_not_offered"  # type: ignore[index]
    assert payload["preflight"]["checks"][1]["role"] == "feature_architect"  # type: ignore[index]
    assert payload["selections"]["work_id"] == "feat_001"  # type: ignore[index]
