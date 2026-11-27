"""Feature readiness on backlog feature rows from GET /api/board."""

from __future__ import annotations

import json
import threading
import time
from datetime import date
from http import HTTPStatus

import pytest

import cascade.workspace.integration_worktree as integration_worktree
from cascade.board.parse import render_doc
from cascade.board.store import move_doc
from cascade.board.paths import column_dir, column_for_status, slugify
from cascade.board.types import WorkDoc, WorkMeta
from cascade.boss.view import compute_boss_view
from cascade.war_room.server import serve
from cascade.war_room.room_settings import write_stacked_pr_enabled
from tests.support import FEATURE_BODY, add_doc, approve_board_feature, make_repo
from tests.war_room.test_http_read import _free_port, _get


def _feature_row(payload: dict, feature_id: str) -> dict:
    for column in ("1_backlog", "2_active", "3_completed"):
        for row in payload["features"][column]:
            if row["id"] == feature_id:
                return row
    raise KeyError(feature_id)


def _has_blocker(blockers: list[str], code: str) -> bool:
    prefix = code + ":"
    return any(item == code or item.startswith(prefix) for item in blockers)


def _write_parentless_feature(root, *, id: str, title: str) -> None:
    column = column_for_status("backlog")
    path = root / column_dir("feature", column) / f"{id}_{slugify(title)}.md"
    doc = WorkDoc(
        meta=WorkMeta(
            id=id,
            title=title,
            tier="feature",
            status="backlog",
            parent=None,
            children=[],
            depends_on=[],
            owners=["tester"],
            skills=[],
            parent_rev=None,
            created=date(2026, 10, 9),
            updated=date(2026, 10, 9),
            path=path,
        ),
        body=FEATURE_BODY,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_doc(doc), encoding="utf-8")


@pytest.fixture
def war_room_server(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = make_repo(tmp_path, git=False)
    # Provider selection is outside this projection fixture. Keep the approval
    # action's dependency boundary real while isolating its unrelated preflight.
    monkeypatch.setattr(
        "cascade.approvals._require_approval_selections", lambda *_args, **_kwargs: ()
    )
    add_doc(root, id="epic_001", title="Active epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Needs approval",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Dependency",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_003",
        title="Waiting on dep",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_002"],
    )
    add_doc(
        root,
        id="feat_004",
        title="Ready",
        tier="feature",
        parent="epic_001",
    )
    _write_parentless_feature(root, id="feat_005", title="No parent epic")
    # Approval is an action boundary: establish the dependency as satisfied,
    # approve the current plan, then restore the waiting state projected here.
    move_doc("feat_002", "completed", root=root)
    approve_board_feature(root, "feat_003")
    move_doc("feat_002", "backlog", root=root)
    approve_board_feature(root, "feat_004")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_board_serializes_backlog_feature_readiness(war_room_server) -> None:
    base, root, _server = war_room_server
    status, payload, _headers = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK

    unapproved = _feature_row(payload, "feat_001")
    assert unapproved["readiness"]["approved"] is False
    assert unapproved["readiness"]["approval"] == {
        "result": "approval_required",
        "eligibility": "eligible",
        "state": "unapproved",
        "eligible": True,
        "explanation": "Current predecessor evidence permits approval.",
        "affected_work_ids": ["feat_001"],
    }
    assert _has_blocker(unapproved["readiness"]["blockers"], "not_approved")

    waiting = _feature_row(payload, "feat_003")
    assert waiting["readiness"]["approved"] is True
    assert waiting["readiness"]["approval"]["state"] == "approved"
    assert waiting["readiness"]["approval"]["result"] == "approved"
    assert waiting["readiness"]["approval"]["eligibility"] == "eligible_waiting"
    assert _has_blocker(waiting["readiness"]["blockers"], "unmet_deps")
    assert any("feat_002" in item for item in waiting["readiness"]["blockers"])

    ready = _feature_row(payload, "feat_004")
    assert ready["readiness"]["approved"] is True
    assert ready["readiness"]["blockers"] == []

    orphan = _feature_row(payload, "feat_005")
    assert _has_blocker(orphan["readiness"]["blockers"], "epic_inactive")

    boss = compute_boss_view(root=root)
    assert "feat_004" in boss.dispatchable_features
    assert "feat_005" not in boss.dispatchable_features


def test_feature_plan_doc_reuses_board_readiness_projection(war_room_server) -> None:
    base, _root, _server = war_room_server
    board_status, board, _headers = _get(f"{base}/api/board")
    doc_status, doc, _headers = _get(f"{base}/api/doc/feat_001")

    assert board_status == HTTPStatus.OK
    assert doc_status == HTTPStatus.OK
    plan_readiness = doc["feature_readiness"]
    board_readiness = _feature_row(board, "feat_001")["readiness"]
    assert plan_readiness["approval"] == board_readiness["approval"]
    assert plan_readiness["blockers"] == board_readiness["blockers"]
    assert [row["code"] for row in plan_readiness["explanation"]["reasons"]] == [
        row["code"] for row in board_readiness["explanation"]["reasons"]
    ]


def test_feature_plan_approval_submits_displayed_context_once(
    war_room_server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive the plan-page control through real loopback GET/POST boundaries."""

    playwright = pytest.importorskip("playwright.sync_api")
    base, _root, _server = war_room_server
    started = threading.Event()
    release = threading.Event()
    posts: list[tuple[str, object]] = []
    context = {
        "owner_work_id": "feat_001",
        "target_repository_key": "target-fixture",
        "plan_revision": "a" * 40,
        "review_unit_id": "review-plan-current",
        "reviewed_tuple_digest": "b" * 64,
        "accepted_baseline_generation": 9,
    }

    monkeypatch.setattr(
        "cascade.war_room.architecture_routes.review_envelope",
        lambda _root, work_id, _tier: {
            "owner_work_id": work_id,
            "state": "ready",
            "approval_context": {**context, "owner_work_id": work_id},
            "views": [],
        },
    )

    def approve_feature(work_id, *, root, review_context):  # type: ignore[no-untyped-def]
        posts.append((work_id, review_context))
        started.set()
        assert release.wait(timeout=10)
        return {
            "ok": True,
            "approval_result": "approved",
            "approval_state": "approved",
            "approval_explanation": {
                "code": "approval_saved_waiting",
                "message": "Approval saved; predecessor completion is still required.",
            },
            "affected_work_ids": ["feat_001", "feat_002"],
            "execution_state": "waiting",
            "dispatch_pending": True,
        }

    monkeypatch.setattr("cascade.approvals.approve_feature", approve_feature)

    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"chromium is unavailable: {exc}")
        page = browser.new_page()
        try:
            page.goto(f"{base}/plan/feat_001", wait_until="domcontentloaded")
            approve = page.get_by_role("button", name="Approve feature for feat_001")
            approve.wait_for()
            scope = page.locator(".feature-plan-approval-scope")
            assert context["plan_revision"] in scope.inner_text()
            assert context["review_unit_id"] in scope.inner_text()
            assert context["reviewed_tuple_digest"] in scope.inner_text()

            approve.focus()
            approve.press("Enter")
            assert started.wait(timeout=5)
            pending = page.get_by_role("button", name="Approving… for feat_001")
            assert pending.is_disabled()
            pending.evaluate("element => element.click()")
            assert len(posts) == 1
            release.set()
            page.wait_for_function(
                """() => document.querySelector('.feature-plan-approval-status')
                  ?.textContent.includes('approval_saved_waiting')"""
            )
            assert "Affected: feat_001, feat_002." in page.locator(
                ".feature-plan-approval-status"
            ).inner_text()
            assert posts[0][0] == "feat_001"
            assert posts[0][1].to_dict() == context
        finally:
            release.set()
            browser.close()


def test_board_endpoint_reuses_one_board_scan(
    war_room_server, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, root, _server = war_room_server
    integration_worktree.invalidate_merged_board(root)
    monkeypatch.setattr(integration_worktree, "_MERGED_BOARD_CACHE_TTL_S", 0.0)
    scans = 0
    original = integration_worktree._merged_board_uncached

    def counting_scan(trunk, *, readonly=False):
        nonlocal scans
        if not readonly:
            scans += 1
        return original(trunk, readonly=readonly)

    monkeypatch.setattr(integration_worktree, "_merged_board_uncached", counting_scan)
    status, _payload, _headers = _get(f"{base}/api/board")

    assert status == HTTPStatus.OK
    assert scans == 1


def test_board_snapshot_preserves_pending_review_blockers(war_room_server) -> None:
    base, root, _server = war_room_server
    write_stacked_pr_enabled("epic_001", False, root=root)
    move_doc("feat_002", "completed", root=root)
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"feat_002": {"url": "https://example.test/pull/2", "closed": False}}),
        encoding="utf-8",
    )

    status, payload, _headers = _get(f"{base}/api/board")

    assert status == HTTPStatus.OK
    dependent = _feature_row(payload, "feat_003")
    sibling = _feature_row(payload, "feat_004")
    assert _has_blocker(dependent["readiness"]["blockers"], "feature_awaiting_merge")
    assert _has_blocker(sibling["readiness"]["blockers"], "sibling_blocked")


def test_approved_feature_waits_for_sibling_then_refreshes_without_reapproval(
    war_room_server,
) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    base, root, _server = war_room_server
    move_doc("feat_002", "active", root=root)

    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
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
            row = page.locator('.board-row[data-id="feat_004"]')
            row.wait_for(state="visible")

            readiness = row.locator(".feature-readiness")
            assert readiness.get_attribute("aria-label") == "Activation readiness for feat_004"
            disclosure = readiness.locator("summary")
            disclosure.press("Enter")
            assert readiness.locator("details").evaluate("element => element.open") is True
            assert "Another feature in this Epic is actively executing." in readiness.inner_text()
            assert "Affected: feat_002." in readiness.inner_text()
            assert "The feature is approved." in readiness.inner_text()
            assert readiness.locator('a[href="/plan/feat_002"]').count() == 1
            assert row.get_by_role("button", name="Approve feature").count() == 0

            move_doc("feat_002", "completed", root=root)
            page.wait_for_function(
                """() => {
                  const row = document.querySelector('.board-row[data-id="feat_004"]');
                  return row && !row.textContent.includes('Another feature in this Epic is actively executing.');
                }""",
                timeout=10_000,
            )

            refreshed = page.locator('.board-row[data-id="feat_004"] .feature-readiness')
            refreshed.locator("summary").press("Enter")
            assert "No sibling feature is actively executing." in refreshed.inner_text()
            assert "The feature is approved." in refreshed.inner_text()
            assert page.locator(
                '.board-row[data-id="feat_004"] button', has_text="Approve feature"
            ).count() == 0
            assert approval_requests == []
        finally:
            browser.close()


def test_feature_approval_action_survives_rerenders_and_announces_typed_outcomes(
    war_room_server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive the real board DOM and loopback POST boundary with delayed writes."""

    playwright = pytest.importorskip("playwright.sync_api")
    base, root, _server = war_room_server
    add_doc(
        root,
        id="feat_006",
        title="Unknown transport",
        tier="feature",
        parent="epic_001",
    )
    approval_started = threading.Event()
    release_approval = threading.Event()
    posts: list[tuple[str, object]] = []
    context = {
        "owner_work_id": "feat_001",
        "target_repository_key": "target-fixture",
        "plan_revision": "a" * 40,
        "review_unit_id": "review-fixture-1",
        "reviewed_tuple_digest": "b" * 64,
        "accepted_baseline_generation": 7,
    }

    def review_projection(_root, work_id, **_kwargs):  # type: ignore[no-untyped-def]
        return {
            "owner_work_id": work_id,
            "state": "ready",
            "approval_context": {**context, "owner_work_id": work_id},
            "views": [],
            "pagination": {"cursor": 0, "limit": 1, "total": 0, "next_cursor": None},
        }

    def approve_feature(work_id, *, root, review_context):  # type: ignore[no-untyped-def]
        posts.append((work_id, review_context))
        if work_id == "feat_002":
            from cascade.planning_action_dependencies import DependencyActionRefused

            raise DependencyActionRefused(
                "dependency_unmet",
                reasons=("predecessor incomplete",),
                affected_work_ids=("feat_002", "feat_005"),
            )
        approval_started.set()
        assert release_approval.wait(timeout=10)
        return {
            "ok": True,
            "approval_result": "approved",
            "approval_state": "approved",
            "approval_explanation": {
                "code": "approval_saved_waiting",
                "message": "Approval saved; predecessor completion is still required.",
            },
            "affected_work_ids": ["feat_001", "feat_002"],
            "execution_state": "waiting",
            "dispatch_pending": True,
        }

    monkeypatch.setattr(
        "cascade.war_room.architecture_routes.review_projection", review_projection
    )
    monkeypatch.setattr("cascade.approvals.approve_feature", approve_feature)

    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"chromium is unavailable: {exc}")
        page = browser.new_page()
        try:
            page.goto(base, wait_until="domcontentloaded")
            row = page.locator('.board-row[data-id="feat_001"]')
            load = row.get_by_role("button", name="Load approval scope")
            load.focus()
            load.press("Enter")
            approve = page.locator(
                '.board-row[data-id="feat_001"] button', has_text="Approve feature"
            )
            approve.wait_for()
            scope = page.locator('.board-row[data-id="feat_001"] .feature-approval-scope')
            assert context["plan_revision"] in scope.inner_text()
            assert context["review_unit_id"] in scope.inner_text()
            assert context["reviewed_tuple_digest"] in scope.inner_text()
            assert approve.evaluate("element => document.activeElement === element") is True

            approve.press("Enter")
            assert approval_started.wait(timeout=5)
            pending = page.locator(
                '.board-row[data-id="feat_001"] button', has_text="Approving…"
            )
            pending.wait_for()
            assert pending.is_disabled()
            pending.evaluate("element => element.click()")
            # A board poll can replace the row while the POST remains in flight.
            page.evaluate("() => window.dispatchEvent(new Event('focus'))")
            time.sleep(0.1)
            assert len(posts) == 1
            release_approval.set()
            outcome = page.locator(
                '.board-row[data-id="feat_001"] .feature-approval-feedback'
            )
            page.wait_for_function(
                """() => document.querySelector('.board-row[data-id="feat_001"] .feature-approval-feedback')
                  ?.textContent.includes('Approval approved · state approved · execution waiting')"""
            )
            assert "Affected: feat_001, feat_002." in outcome.inner_text()
            assert page.locator(
                '.board-row[data-id="feat_001"] button[data-feature-approval-action]'
            ).count() == 0
            assert posts[0][1].to_dict() == context

            refused = page.locator('.board-row[data-id="feat_002"]')
            refused.get_by_role("button", name="Load approval scope").click()
            refused.get_by_role("button", name="Approve feature").click()
            page.wait_for_function(
                """() => document.querySelector('.board-row[data-id="feat_002"] .feature-approval-feedback')
                  ?.textContent.includes('Approval refused')"""
            )
            assert "Affected: feat_002, feat_005." in refused.inner_text()
            assert refused.get_by_role("button", name="Retry approval").count() == 1
            # The explicit refusal remains row-local through a canonical poll.
            page.wait_for_timeout(3_200)
            refused = page.locator('.board-row[data-id="feat_002"]')
            assert "Approval refused" in refused.inner_text()
            assert refused.get_by_role("button", name="Retry approval").count() == 1

            def abort_unknown(route):  # type: ignore[no-untyped-def]
                payload = route.request.post_data_json
                if payload and payload.get("id") == "feat_006":
                    route.abort("connectionfailed")
                else:
                    route.continue_()

            page.route("**/api/approve_feature", abort_unknown)
            unknown = page.locator('.board-row[data-id="feat_006"]')
            unknown.get_by_role("button", name="Load approval scope").click()
            unknown.get_by_role("button", name="Approve feature").click()
            page.wait_for_function(
                """() => document.querySelector('.board-row[data-id="feat_006"] .feature-approval-feedback')
                  ?.textContent.includes('Canonical board evidence remains unapproved')"""
            )
            unknown = page.locator('.board-row[data-id="feat_006"]')
            assert "Approval unknown" in unknown.inner_text()
            assert unknown.get_by_role("button", name="Retry approval").count() == 1
            assert [work_id for work_id, _context in posts].count("feat_006") == 0
            page.unroute("**/api/approve_feature", abort_unknown)
            unknown.get_by_role("button", name="Retry approval").click()
            page.wait_for_function(
                """() => document.querySelector('.board-row[data-id="feat_006"] .feature-approval-feedback')
                  ?.textContent.includes('Approval approved')"""
            )
            assert [work_id for work_id, _context in posts].count("feat_006") == 1
        finally:
            release_approval.set()
            browser.close()
