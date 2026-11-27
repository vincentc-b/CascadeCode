"""Real-browser proof for receipt-backed, deferred Feature dispatch."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.approvals import canonical_feature_approval_state, feature_approved
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from tests.support import approve_epic_plan_when_ready
from cascade.automation import reconcile_approval_dispatch, reset_automation_memory
from cascade.board.store import move_doc, read_doc
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, dispatch_feature, read_events
from cascade.workspace.integration_worktree import get_integration_worktree
from cascade.workspace.kickoff import install_kickoff, wait_for_background_kickoffs
from tests.support import add_doc, commit_board, make_repo
from tests.war_room.test_board_feature_readiness import _feature_row, _has_blocker
from tests.war_room.test_dispatch_routes import _get, _post
from tests.war_room.test_http_read import _free_port


@pytest.fixture(autouse=True)
def supported_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    now = time.time()
    inventory = ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id="offered", display_name="Offered"),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, now, now + 300, 300),
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )


def _select_supported(root: Path, work_id: str) -> None:
    doc = read_doc(work_id, root=root)
    roles = {
        "epic": (
            "epic_manager",
            "epic_architect",
            "feature_lead",
            "feature_architect",
            "swe",
        ),
        "feature": ("feature_lead", "feature_architect", "swe"),
        "task": ("swe",),
    }[doc.meta.tier]
    doc.meta.provider = "codex"
    doc.meta.models = {role: "offered" for role in roles}
    from cascade.board.store import write_doc

    write_doc(doc, root=root)


def _initial_commit(root: Path) -> None:
    subprocess.run(
        ["git", "config", "init.defaultBranch", "main"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _enable_automation(root: Path) -> None:
    root.joinpath("cascade.toml").write_text(
        "[automation]\nenabled = true\n",
        encoding="utf-8",
    )


def _ready_to_plan_events(feature_id: str, *, root: Path) -> list[object]:
    events, _ = read_events(feature_id, 0, root=root)
    return [event for event in events if event.type == "FeatureReadyToPlan"]


def _task_dispatch_events(task_id: str, *, root: Path) -> list[object]:
    events, _ = read_events(task_id, 0, root=root)
    return [event for event in events if event.type == "TaskDispatched"]


def _execution_lease_count(root: Path) -> int:
    from cascade.task.execution import _read

    return len(_read(root))


def _approve_initial_epic_plan(
    root: Path,
    *,
    epic_id: str = "epic_001",
    feature_id: str = "feat_001",
) -> None:
    add_doc(root, id=epic_id, title="Active epic", tier="epic", status="ready_to_plan")
    add_doc(root, id=feature_id, title="Initial child", tier="feature", parent=epic_id)
    _select_supported(root, epic_id)
    _select_supported(root, feature_id)
    commit_board(root)
    assert activate_epic(epic_id, "human", root=root).ok
    approve_epic_plan_when_ready(epic_id, root=root)
    assert feature_approved(feature_id, root=root)
    reset_automation_memory()


def _start_war_room(root: Path) -> tuple[str, object, threading.Thread]:
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", server, thread


def _shutdown(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_late_minted_feature_approval_and_single_dispatch_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)

    kickoff_work_ids: list[str] = []

    def stub_run_kickoff(reason, repo):  # type: ignore[no-untyped-def]
        kickoff_work_ids.append(reason.work_id)

    monkeypatch.setattr("cascade.workspace.kickoff._run_kickoff", stub_run_kickoff)

    late_ok_dispatches: list[str] = []
    real_dispatch = dispatch_feature

    def counting_dispatch(work_id: str, by: str, *, root=None):  # type: ignore[no-untyped-def]
        result = real_dispatch(work_id, by, root=root)
        if work_id == "feat_051_006" and result.ok:
            late_ok_dispatches.append(by)
        return result

    monkeypatch.setattr("cascade.automation.dispatch_feature", counting_dispatch)

    root = make_repo(tmp_path, git=True)
    _enable_automation(root)
    _initial_commit(root)
    _approve_initial_epic_plan(
        root, epic_id="epic_051", feature_id="feat_051_005"
    )
    assert read_doc("feat_051_005", root=root).meta.path.parent.name == "2_active"
    add_doc(
        root,
        id="feat_051_006",
        title="Approved but deferred child",
        tier="feature",
        parent="epic_051",
        depends_on=["feat_051_005"],
        children=["task_051_006_001"],
    )
    add_doc(
        root,
        id="task_051_006_001",
        title="Must not start before the Feature",
        tier="task",
        parent="feat_051_006",
    )
    _select_supported(root, "feat_051_006")
    _select_supported(root, "task_051_006_001")
    commit_board(root)
    assert not feature_approved("feat_051_006", root=root)

    review_context = {
        "owner_work_id": "feat_051_006",
        "target_repository_key": "target-fixture",
        "plan_revision": "a" * 40,
        "review_unit_id": "review-feat-051-006",
        "reviewed_tuple_digest": "b" * 64,
        "accepted_baseline_generation": 1,
    }

    def review_projection(_root, work_id, **_kwargs):  # type: ignore[no-untyped-def]
        return {
            "owner_work_id": work_id,
            "state": "ready",
            "approval_context": {**review_context, "owner_work_id": work_id},
            "views": [],
            "pagination": {"cursor": 0, "limit": 1, "total": 0, "next_cursor": None},
        }

    monkeypatch.setattr(
        "cascade.war_room.architecture_routes.review_projection", review_projection
    )

    base, server, thread = _start_war_room(root)
    install_kickoff(root)
    kickoff_work_ids.clear()
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            _shutdown(server, thread)
            pytest.skip(f"chromium is unavailable: {exc}")
        page = browser.new_page()
        approval_requests: list[str] = []
        page.on(
            "request",
            lambda request: approval_requests.append(request.url)
            if "/api/approve_feature" in request.url
            else None,
        )
        try:
            page.goto(base, wait_until="domcontentloaded")
            row = page.locator('.board-row[data-id="feat_051_006"]')
            row.wait_for(state="visible")
            row.get_by_role("button", name="Load approval scope").click()
            approve = row.get_by_role("button", name="Approve feature")
            approve.wait_for()
            assert review_context["reviewed_tuple_digest"] in row.locator(
                ".feature-approval-scope"
            ).inner_text()
            approve.click()
            page.wait_for_function(
                """() => document.querySelector('.board-row[data-id="feat_051_006"] .feature-approval-feedback')
                  ?.textContent.includes('Approval approved')"""
            )
            assert len(approval_requests) == 1

            assert canonical_feature_approval_state(
                "feat_051_006", root=root
            ) == "approved"
            assert read_doc("feat_051_006", root=root).meta.path.parent.name == "1_backlog"
            assert len(_ready_to_plan_events("feat_051_006", root=root)) == 0
            assert len(_task_dispatch_events("task_051_006_001", root=root)) == 0
            assert _execution_lease_count(root) == 0

            page.reload(wait_until="domcontentloaded")
            assert page.locator(
                '.board-row[data-id="feat_051_006"] button', has_text="Approve feature"
            ).count() == 0
            assert len(approval_requests) == 1

            _shutdown(server, thread)
            base, server, thread = _start_war_room(root)
            page.goto(base, wait_until="domcontentloaded")
            restarted = page.locator('.board-row[data-id="feat_051_006"]')
            restarted.wait_for(state="visible")
            assert restarted.locator(
                'button[data-feature-approval-action="feat_051_006"]'
            ).count() == 0
            _status, restarted_board = _get(f"{base}/api/board")
            assert _feature_row(restarted_board, "feat_051_006")["readiness"][
                "approval"
            ]["state"] == "approved"
            assert canonical_feature_approval_state(
                "feat_051_006", root=root
            ) == "approved"
            assert len(_ready_to_plan_events("feat_051_006", root=root)) == 0
            assert len(_task_dispatch_events("task_051_006_001", root=root)) == 0
            assert _execution_lease_count(root) == 0

            move_doc("feat_051_005", "completed", root=root)
            commit_board(root, "complete and verify predecessor")
            outcomes = reconcile_approval_dispatch(root)
            assert outcomes["features"] == ["feat_051_006"], outcomes
            assert wait_for_background_kickoffs(timeout=15)

            assert len(approval_requests) == 1
            assert len(late_ok_dispatches) == 1
            assert len(_ready_to_plan_events("feat_051_006", root=root)) == 1
            assert len(_task_dispatch_events("task_051_006_001", root=root)) == 1
            assert _execution_lease_count(root) == 1
            assert read_doc("feat_051_006", root=root).meta.path.parent.name == "2_active"
            assert get_integration_worktree(
                root, "feature", "feat_051_006"
            ) is not None

            repeated = reconcile_approval_dispatch(root)
            assert repeated == {"features": [], "tasks": []}
            assert len(late_ok_dispatches) == 1
            assert len(_ready_to_plan_events("feat_051_006", root=root)) == 1
            assert len(_task_dispatch_events("task_051_006_001", root=root)) == 1
            assert _execution_lease_count(root) == 1
        finally:
            browser.close()
            _shutdown(server, thread)


def test_late_mint_approval_blocked_by_unmerged_dependency_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)

    root = make_repo(tmp_path, git=True)
    _enable_automation(root)
    _initial_commit(root)
    _approve_initial_epic_plan(root)
    write_stacked_pr_enabled("epic_001", False, root=root)
    epic_worktree = get_integration_worktree(root, "epic", "epic_001")
    assert epic_worktree is not None
    add_doc(
        epic_worktree.path,
        id="feat_003",
        title="Open sibling",
        tier="feature",
        parent="epic_001",
    )
    commit_board(epic_worktree.path, "mint predecessor")
    add_doc(
        root,
        id="feat_002",
        title="Late mint",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_003"],
    )
    _select_supported(root, "feat_002")
    commit_board(root)

    base, server, thread = _start_war_room(root)
    try:
        _status, board = _get(f"{base}/api/board")
        late_row = _feature_row(board, "feat_002")
        assert late_row["readiness"]["approved"] is False
        assert late_row["readiness"]["approval"]["state"] == "unapproved"
        assert late_row["readiness"]["approval"]["result"] == "approval_required"
        assert late_row["readiness"]["approval"]["eligibility"] == "eligible_waiting"
        assert late_row["readiness"]["approval"]["eligible"] is True
        assert late_row["readiness"]["approval"]["affected_work_ids"] == ["feat_003"]

        status, body = _post(f"{base}/api/approve_feature", {"id": "feat_002"})
        assert status == HTTPStatus.OK
        assert body["newly_approved"] is True
        assert body["approval_result"] == "approved"
        assert body["approval_state"] == "approved"
        assert body["execution_state"] == "waiting"
        assert body["dispatch_pending"] is True
        assert body["approval_explanation"]["code"] == "approval_saved_waiting"
        assert set(body["affected_work_ids"]) == {"feat_001", "feat_002", "feat_003"}
        assert feature_approved("feat_002", root=root)
        assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"
        assert len(_ready_to_plan_events("feat_002", root=root)) == 0

        _status, board = _get(f"{base}/api/board")
        late_row = _feature_row(board, "feat_002")
        blockers = late_row["readiness"]["blockers"]
        assert late_row["readiness"]["approval"]["state"] == "approved"
        assert late_row["readiness"]["approval"]["result"] == "approved"
        assert late_row["readiness"]["approval"]["eligibility"] == "eligible_waiting"
        assert _has_blocker(blockers, "unmet_deps")
        assert any(item.startswith("unmet_deps:feat_003") for item in blockers)

        # Lifecycle completion clears the declared predecessor but cannot erase
        # the independent active-sibling and intended-target integration gates.
        move_doc("feat_003", "completed", root=root)
        _status, board = _get(f"{base}/api/board")
        late_row = _feature_row(board, "feat_002")
        blockers = late_row["readiness"]["blockers"]
        assert not _has_blocker(blockers, "unmet_deps")
        assert _has_blocker(blockers, "sibling_blocked")
        assert len(_ready_to_plan_events("feat_002", root=root)) == 0

        # A review for the wrong source branch is evidence of a review wait,
        # never proof that the intended Feature source was integrated.
        review_state = root / ".cascade" / "reviews.json"
        review_state.parent.mkdir(parents=True, exist_ok=True)
        review_state.write_text(
            json.dumps(
                {
                    "feat_003": {
                        "url": "https://github.example/pull/51",
                        "closed": False,
                        "source_branch": "feat/feat_051_mismatched",
                        "target_branch": "epic/epic_001",
                    }
                }
            ),
            encoding="utf-8",
        )
        _status, board = _get(f"{base}/api/board")
        blockers = _feature_row(board, "feat_002")["readiness"]["blockers"]
        assert _has_blocker(blockers, "feature_awaiting_merge")
        assert len(_ready_to_plan_events("feat_002", root=root)) == 0

        with playwright.sync_playwright() as runtime:
            try:
                browser = runtime.chromium.launch(headless=True)
            except playwright.Error as exc:
                pytest.skip(f"chromium is unavailable: {exc}")
            page = browser.new_page()
            try:
                page.goto(base, wait_until="domcontentloaded")
                row = page.locator('.board-row[data-id="feat_002"]')
                row.wait_for(state="visible")
                row.locator(".feature-readiness summary").click()
                text = row.locator(".feature-readiness").inner_text()
                assert "Another feature in this Epic is actively executing." in text
                assert "Feature work is waiting for required merge or review." in text
                assert "feat_001" in text
                assert "feat_003" in text
            finally:
                browser.close()
    finally:
        _shutdown(server, thread)


def test_late_mint_approval_blocked_when_dependency_sibling_in_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)

    root = make_repo(tmp_path, git=True)
    _enable_automation(root)
    _initial_commit(root)
    _approve_initial_epic_plan(root)
    add_doc(
        root,
        id="feat_003",
        title="Sibling in review",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    state = root / ".cascade" / "reviews.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps(
            {
                "feat_003": {
                    "url": "https://github.example/pull/9",
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )
    add_doc(
        root,
        id="feat_002",
        title="Late mint",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_003"],
    )
    _select_supported(root, "feat_002")
    commit_board(root)

    base, server, thread = _start_war_room(root)
    try:
        status, body = _post(f"{base}/api/approve_feature", {"id": "feat_002"})
        assert status == HTTPStatus.OK
        assert body["newly_approved"] is True
        assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"

        _status, board = _get(f"{base}/api/board")
        blockers = _feature_row(board, "feat_002")["readiness"]["blockers"]
        assert _has_blocker(blockers, "feature_awaiting_merge") or _has_blocker(
            blockers, "sibling_blocked"
        )
    finally:
        _shutdown(server, thread)
