"""Server-rendered War Room home page (task_011)."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.board.store import list_board, move_doc
from cascade.war_room.serialize import board_view_from_index
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get_html(url: str) -> tuple[int, str, dict[str, str]]:
    with urllib.request.urlopen(url) as resp:
        raw = resp.read().decode()
        return resp.status, raw, dict(resp.headers)


@pytest.fixture
def ui_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="epic_002", title="Second epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_002")
    add_doc(root, id="task_001", title="Work item", tier="task", parent="feat_001", status="active")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_get_home_is_server_rendered_html(ui_server):
    base, _root = ui_server
    for path in ("/", "/war-room"):
        status, html, headers = _get_html(f"{base}{path}")
        assert status == HTTPStatus.OK
        content_type = headers.get("Content-type", headers.get("Content-Type", ""))
        assert "text/html" in content_type
        assert 'id="war-room-board"' in html
        assert 'id="epic-war-room-chat"' in html
        assert 'id="recovery-current-summary"' in html
        assert 'id="toast-stream"' in html
        assert 'id="supervisor-status-banner"' in html
        assert "Branch pattern: task/" in html
        assert 'id="branch-label-example">task_001<' in html
        assert "Timed out after 10s" in html
        assert "load-deadline-banner" in html
        # The shared page must load both audit and architecture dependencies
        # before starting the board; each script must execute only once.
        scripts = (
            "/static/audit_status_ui.js",
            "/static/vendor/marked.min.js",
            "/static/plan_viewer.js",
            "/static/architecture_tab.js",
            "/static/war_room.js",
        )
        for script in scripts:
            assert html.count('src="' + script) == 1
        assert [html.index(script) for script in scripts] == sorted(
            html.index(script) for script in scripts
        )


def test_default_epic_from_active_column(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'data-default-epic-graph-id="epic_002"' in html


def test_features_lens_empty_marker_in_html(ui_server):
    """Features tier exposes stable epic-lens empty copy (task_054)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert "data-board-features-lens-empty" in html
    assert "No epic is active or selected." in html


def test_completed_feature_awaiting_review_remains_in_active_lane(ui_server):
    base, root = ui_server
    move_doc("feat_001", "completed", root=root)
    state = root / ".cascade" / "reviews.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/pull/4",
                    "number": "4",
                    "forge": "github",
                    "source_branch": "feat/feat_001",
                    "target_branch": "epic/epic_002",
                    "draft": False,
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )

    _status, raw, _headers = _get_html(f"{base}/api/board")
    board = json.loads(raw)

    active = {item["id"]: item for item in board["features"]["2_active"]}
    completed = {item["id"] for item in board["features"]["3_completed"]}
    review = active["feat_001"]["review"]
    assert {key: review[key] for key in ("state", "url", "number", "draft")} == {
        "state": "awaiting_review",
        "url": "https://github.example/pull/4",
        "number": "4",
        "draft": False,
    }
    assert review["implementation_complete"] is True
    assert review["delivery_status"] == "review_pending"
    assert review["repair"]["generation"] == 0
    assert "feat_001" not in completed


def test_tasks_lens_empty_marker_in_html(ui_server):
    """Tasks tier exposes stable feature-lens empty copy (task_055)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert "data-board-tasks-lens-empty" in html
    assert "Select a feature" in html


def test_completed_column_collapse_controls_in_html(ui_server):
    """Completed columns expose stable collapse markers (task_053)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert html.count("data-board-completed-collapse") == 3
    assert html.count("board-completed-collapse") >= 3
    for tier in ("epics", "features", "tasks"):
        assert f'data-board-tier="{tier}"' in html
    epics_tier = html.split('data-tier="epics"')[1].split('data-tier="features"')[0]
    assert "data-board-completed-history" in epics_tier
    assert 'aria-expanded="false"' in epics_tier
    assert "Expand" in epics_tier
    assert "board-column-completed-collapsed" in epics_tier
    assert html.index("/static/board_focus.js") < html.index("/static/open_reviews_pane.js")
    assert html.index("/static/brief_defaults_ui.js") < html.index("/static/war_room.js")
    assert html.index("/static/open_reviews_pane.js") < html.index("/static/war_room.js")


def test_war_room_js_renders_completed_epics_history_link():
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")
    assert "renderCompletedEpicsHistory" in source
    assert "completed_epics_history" in source
    assert "board-action-link-unavailable" in source
    assert "Repository history link unavailable." in source


def test_war_room_js_renders_toast_body():
    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")
    assert "toast.body" in source
    assert "toast.kind" in source
    assert "View plan" in source
    assert "/plan/" in source
    assert "Nothing in flight." in source
    assert "item.plan_approved" in source
    assert '"Approved"' in source
    assert 'approved.classList.add("approval-confirmed")' in source
    assert "EpicPlanReadinessUi" in source
    assert "appendPlanEntryStatusToRow" in source
    assert "approvePlanDisabledReason" in source
    assert '"Awaiting review"' in source
    assert 'item.review.state === "awaiting_integration"' in source
    assert 'item.review.state === "awaiting_closeout"' in source
    assert '"View merged review" : "Open review", item.review.url' in source
    assert "EPIC_CLOSE_DEADLINE_MS = 60000" in source
    assert 'setStatus("Closing epic " + epicId + "…", false)' in source
    assert '"Epic close timed out after 60s"' in source


def test_feature_readiness_ui_cases():
    if shutil.which("node") is None:
        pytest.skip("node is required for browser-side UI contract tests")
    cases = Path(__file__).with_name("feature_readiness_ui_cases.mjs")
    result = subprocess.run(["node", str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_war_room_js_renders_canonical_recovery_incident_once_per_transition():
    source = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    ).read_text(encoding="utf-8")

    assert "appendRecoveryProgressSummary(" in source
    assert 'requested_queued: "Queued · not executing"' in source
    assert 'verification_pending: "Verification pending"' in source
    assert 'verified_complete: "Authoritatively verified"' in source
    assert 'appendRecoveryIncidentLine(block, "Prerequisite", entry.prerequisite)' in source
    assert 'appendRecoveryIncidentLine(block, "Next safe step", entry.next_step)' in source
    assert 'target.kind === "review" ? "Open recovery review" : "Open recovery action"' in source
    assert "RECOVERY_TOASTS_STORAGE_KEY" in source
    assert "recoveryIncidentTransitions[key] === incident.state" in source
    assert "if (!active[key]) delete recoveryIncidentTransitions[key]" in source


def test_recovery_incident_lifecycle_browser_cases():
    if shutil.which("node") is None:
        pytest.skip("node is required for browser-side UI contract tests")
    cases = Path(__file__).with_name("recovery_incident_lifecycle_cases.mjs")
    result = subprocess.run(["node", str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_recovery_progress_current_summary_browser_cases():
    if shutil.which("node") is None:
        pytest.skip("node is required for browser-side UI contract tests")
    cases = Path(__file__).with_name("recovery_progress_current_cases.mjs")
    result = subprocess.run(["node", str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_war_room_js_renders_and_submits_epic_return_control():
    source = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    ).read_text(encoding="utf-8")

    assert "appendEpicReturnFeedback(row, item.return_to_backlog)" in source
    assert 'actionButton("Return to backlog"' in source
    assert 'apiPost("/api/return_epic_to_backlog"' in source
    assert "epic_id: item.id" in source
    assert "request_id: returnRequestId()" in source
    assert "returnRefusalMessages(body.eligibility)" in source


def test_board_projects_safe_provider_recovery_for_active_work(tmp_path, monkeypatch):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    (root / ".cascade").mkdir(exist_ok=True)
    (root / ".cascade" / "provider_blockers.json").write_text(
        json.dumps(
            {
                "version": 1,
                "blockers": {
                    "task_001": {
                        "work_id": "task_001",
                        "active": True,
                        "classification": "transient",
                        "reason_code": "provider_unavailable",
                        "message": "credential=do-not-expose",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cascade.feature.recovery.recovery_status", lambda *_args, **_kwargs: None
    )

    task = board_view_from_index(list_board(root), root=root)["tasks"]["2_active"][0]
    recovery = task["provider_recovery"]

    assert recovery["reason"] == (
        "The selected provider is unavailable. Check provider setup or credentials, then retry."
    )
    assert "do-not-expose" not in repr(recovery)
    assert recovery["actions"]["change_provider"] == {"eligible": True}
    assert recovery["actions"]["retry"] == {"eligible": True}
    assert recovery["actions"]["provider_setup"] == {"eligible": True}
    assert recovery["actions"]["return_to_backlog"]["reason_code"] == "not_epic"


def test_war_room_js_renders_only_eligible_provider_recovery_controls():
    source = (
        Path(__file__).resolve().parents[2]
        / "cascade"
        / "war_room"
        / "static"
        / "war_room.js"
    ).read_text(encoding="utf-8")

    assert "appendProviderRecoveryFeedback(row, item.provider_recovery)" in source
    assert 'providerRecoveryAction(providerRecovery, "change_provider")' in source
    assert 'providerRecoveryAction(providerRecovery, "retry")' in source
    assert 'providerRecoveryAction(providerRecovery, "provider_setup")' in source
    assert 'providerRecoveryAction(providerRecovery, "continue_without_flex")' in source
    assert 'actionButton("Continue without Flex"' in source
    assert '"/api/provider-recovery/" + encodeURIComponent(item.id) + "/change"' in source
    assert '"/api/provider-recovery/" + encodeURIComponent(item.id) + "/retry"' in source
    assert '"/continue-without-flex"' in source
    assert "await refreshBoard();" in source


def test_war_room_js_explains_epic_close_comment_blockers():
    source = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    ).read_text(encoding="utf-8")

    assert 'body.reason === "open_human_comments"' in source
    assert 'body.plan_url || ("/plan/" + epicId + "#plan-comments")' in source


def test_epic_close_review_ui_browser_cases():
    if shutil.which("node") is None:
        pytest.skip("node is required for browser-side UI contract tests")
    case_file = Path(__file__).with_name("epic_close_review_ui_cases.mjs")
    subprocess.run(["node", str(case_file)], check=True)


def test_war_room_loads_durable_epic_close_review_ui():
    html = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "templates" / "war_room.html"
    ).read_text(encoding="utf-8")
    assert html.index("/static/epic_close_review_ui.js") < html.index("/static/war_room.js")

    source = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    ).read_text(encoding="utf-8")
    assert "item.implementation_review" in source
    assert 'actionButton("Close epic"' in source
    assert "await refreshBoard();" in source[source.index("async function confirmEpicComplete") :]


def test_supervisor_health_banner_polls_api_health():
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")

    assert 'apiGet("/api/health")' in source
    assert "pollSupervisorHealth()" in source
    assert 'state !== "serving"' in source
    assert "trunk_lock_warning" in source
    assert "updateSupervisorBanner" in source


def test_task_execution_controls_and_board_polling_are_load_safe():
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")

    assert 'status.setAttribute("aria-label", "Execution status: " + execution.label)' in source
    assert 'label: "Running"' in source
    assert 'label: "Blocked"' in source
    assert 'execution.health || execution.phase' in source
    assert 'label: "No signal"' in source
    assert 'recovery.action === "retry"' in source
    assert '"/api/retry_task"' in source
    assert 'appendRecoveryFeedback(row, item.recovery)' in source
    assert "boardRefreshInFlight = Promise.all([" in source
    assert source.count('apiGet("/api/board') == 1
    assert "return refreshBoard({ refreshRelated: false, forceFresh: false })" in source
    assert "setInterval(pollBoard" not in source
    assert "scheduleBoardPoll(boardPollDelayMs)" in source
    assert "Math.min(BOARD_POLL_MAX_MS, boardPollDelayMs * 2)" in source
    assert 'document.addEventListener("visibilitychange", handleVisibilityChange)' in source
    bootstrap = source[source.index("async function bootstrapWarRoom()") :]
    assert bootstrap.index("Promise.allSettled([") < bootstrap.index(
        "scheduleBoardPoll(boardPollDelayMs)"
    )


def test_startup_does_not_duplicate_board_related_requests():
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")

    bootstrap = source[source.index("async function bootstrapWarRoom()") :]
    assert bootstrap.count("await refreshBoard({ refreshRelated: false });") == 1
    assert "await Promise.allSettled" not in bootstrap
    assert bootstrap.count("refreshRelatedPanels(),") == 1
    assert "refreshFlightReport().catch" not in bootstrap
    assert "refreshBossView();" not in bootstrap
    assert "pollChatSidecar()," not in bootstrap
    assert "relatedRefreshInFlight" in source


def test_war_room_refresh_races():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("war_room_refresh_races.mjs")
    result = subprocess.run([node, str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_backlog_priority_browser_cases():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("backlog_priority_ui_cases.mjs")
    result = subprocess.run([node, str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_war_room_loads_backlog_priority_ui_before_board_script():
    html = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "templates" / "war_room.html"
    ).read_text(encoding="utf-8")
    assert html.index("/static/backlog_priority_ui.js") < html.index("/static/war_room.js")


def test_backlog_cancellation_row_behavior():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("brief_cancel_ui_cases.mjs")
    result = subprocess.run([node, str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_task_execution_status_styles_include_healthy_and_blocked_states():
    css_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.css"
    )
    source = css_path.read_text(encoding="utf-8")

    assert ".task-execution-status-running" in source
    assert ".task-execution-status-healthy" in source
    assert ".task-execution-status-blocked" in source
    assert ".task-execution-status-stuck" in source


def test_epic_chat_compose_markup_and_enter_to_send(ui_server):
    """Epic chat exposes compose ids; Enter sends, Shift+Enter newline (war_room.js)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="chat-compose"' in html
    assert 'id="chat-body"' in html
    assert 'id="chat-send"' in html

    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")
    assert "submitChatCompose" in source
    assert 'ev.key !== "Enter" || ev.shiftKey' in source
    assert "el.chatBody.value = \"\"" in source
    assert "const draft = body" in source


def test_war_room_html_loads_war_room_js(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert "/static/war_room.js" in html
    assert "/static/epic_plan_readiness_ui.js" in html
    assert "/static/dependency_review_ui.js" in html
    assert "/static/dependency_review.css" in html
    assert "/static/dependency_status_ui.js" in html
    assert 'id="dependency-current-summary"' in html
    assert "Historical transcript" in html


def test_epic_plan_readiness_ui_cases():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("epic_plan_readiness_ui_cases.mjs")
    result = subprocess.run([node, str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_dependency_status_ui_distinguishes_current_from_historical():
    """Current refreshes replace status without rewriting dated transcript history."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("dependency_status_ui_cases.mjs")
    result = subprocess.run([node, str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_epic_plan_readiness_integration():
    """Planning readiness UI: disabled reasons, ready transition, stale approval (task_015_002_002)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = Path(__file__).with_name("epic_plan_readiness_integration.mjs")
    result = subprocess.run([node, str(cases)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_plan_page_includes_epic_readiness_host(ui_server):
    base, _root = ui_server
    status, html, _headers = _get_html(f"{base}/plan/epic_001")
    assert status == HTTPStatus.OK
    assert 'id="epic-plan-readiness-host"' in html
    assert "/static/epic_plan_readiness_ui.js" in html
    assert 'id="dependency-review-host"' in html
    assert "/static/dependency_review_ui.js" in html


def test_plan_page_includes_comment_compose(ui_server):
    base, _root = ui_server
    status, html, _headers = _get_html(f"{base}/plan/epic_001")
    assert status == HTTPStatus.OK
    assert 'id="plan-comment-body"' in html
    assert 'id="plan-comment-compose"' in html
    assert "Comment on the whole plan" in html
    assert 'id="plan-comment-compose" class="plan-comment-compose" hidden' not in html


def test_providers_pane_markup_in_html(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="providers-pane"' in html
    assert 'id="providers-list"' in html
    assert "Providers" in html


def test_brief_and_sync_controls_in_html(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="btn-create-brief"' in html
    assert 'id="btn-pull-main"' in html
    assert "Refresh briefs" in html
    assert "app updates are handled separately" in html
    assert 'id="brief-form"' in html
    assert 'id="brief-role-selectors"' in html
    assert 'id="btn-brief-inventory-retry"' in html
    assert 'name="manager_model"' not in html
    assert "Create merge request" in html


def test_open_reviews_pane_markup_in_html(ui_server):
    """Open merge requests panel exposes stable ids (feat_005 / task_012)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="open-reviews-pane"' in html
    assert 'id="open-reviews-list"' in html
    assert 'id="btn-refresh-open-reviews"' in html
    assert 'id="open-reviews-status"' in html
    assert "Open merge requests" in html


def test_health_audit_run_control_markup_in_html(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="btn-run-health-audit"' in html
    assert 'id="audit-run-status"' in html
    assert "Run health audit now" in html


def test_open_reviews_js_queries_authoritative_api_only():
    static = Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static"
    pane_source = (static / "open_reviews_pane.js").read_text(encoding="utf-8")
    war_room_source = (static / "war_room.js").read_text(encoding="utf-8")
    assert 'apiGet("/api/open-reviews")' in pane_source
    assert "function refreshOpenReviews" in pane_source
    assert "function renderOpenReviews" in pane_source
    assert 'actionLink("Open review", review.url)' in pane_source
    assert "localStorage" not in pane_source
    assert "OpenReviewsPane" in war_room_source
    assert "createOpenReviewsPane" in war_room_source


def test_open_review_repair_journey_in_real_browser(ui_server):
    """The explicit action preserves typed stages while every refresh stays GET-only."""
    playwright = pytest.importorskip("playwright.sync_api")
    base, _root = ui_server
    identity = {
        "review_url": "https://github.example/pull/4",
        "review_forge": "github",
        "source_ref": "feat/feat_001",
        "target_ref": "epic/epic_002",
        "observed_source_head": "a" * 40,
        "observed_target_head": "b" * 40,
        "observed_review_generation": 4,
    }

    def review(health, delivery, prerequisite, repair=None):
        return {
            "id": "feat_001",
            "url": identity["review_url"],
            "state": "awaiting_review",
            "context": {
                "feature_id": "feat_001",
                "epic_id": "epic_002",
                "feature_title": "Feature one",
                "epic_title": "Epic two",
            },
            "accountable_feature_id": "feat_001",
            "implementation_complete": True,
            "implementation_status": "completed",
            "delivery_status": delivery,
            "evidence": {
                "health_state": health,
                "freshness": "current",
                "ci": {"policy_status": "available"},
                "feedback": {"approval_state": "waiting"},
            },
            "repair": repair or {"generation": 0},
            "repair_identity": identity,
            "next_prerequisite": prerequisite,
        }

    reads = [
        review("pending", "review_pending", "await_current_review_acceptance"),
        review("failed", "review_pending", "request_review_repair"),
    ]
    held_execution = []
    posts = []
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium unavailable: {exc}")
        try:
            page = browser.new_page()

            def next_held_review():
                # The action result renders before its follow-up GET is dispatched.
                # Let Playwright service the route callback before inspecting it.
                for _ in range(200):
                    if held_execution:
                        assert len(held_execution) == 1
                        return held_execution.pop()
                    page.wait_for_timeout(25)
                pytest.fail("Expected the next open-review refresh")

            def read_reviews(route):
                if reads:
                    route.fulfill(json={"reviews": [reads.pop(0)]})
                else:
                    held_execution.append(route)

            def post_repair(route):
                posts.append(route)

            page.route("**/api/open-reviews", read_reviews)
            page.route("**/api/open-reviews/repair", post_repair)
            page.goto(base)
            card = page.locator('.open-review-card[data-review-id="feat_001"]')
            playwright.expect(card).to_contain_text("CI: pending", timeout=15000)

            page.get_by_role("button", name="Refresh", exact=True).click()
            playwright.expect(card).to_contain_text("CI: failed")
            card.get_by_label("Stable repair request ID for feat_001").fill("review-fix:comment-7")
            card.get_by_label("Repair reason for feat_001").fill("Fix the failing check")
            card.get_by_role("button", name="Request repair").click()
            playwright.expect(card).to_contain_text("Submitting authenticated repair request")
            assert len(posts) == 1
            assert posts[0].request.method == "POST"
            posts[0].fulfill(json={
                "ok": True,
                "admitted": True,
                "acknowledged": True,
                "executing": False,
                "verified": False,
                "next_prerequisite": "feature_queue_checkpoint",
            })
            playwright.expect(card).to_contain_text("Admitted · Next: feature_queue_checkpoint")
            next_held_review().fulfill(json={"reviews": [review(
                "failed", "repair_in_progress", "await_repair_execution",
                {"generation": 1, "admitted": True, "executing": True},
            )]})
            playwright.expect(card).to_contain_text("Delivery: repair_in_progress")
            page.get_by_role("button", name="Refresh", exact=True).click()
            next_held_review().fulfill(json={"reviews": [review(
                "green", "review_pending", "await_human_approval",
                {"generation": 1, "admitted": True, "waiting": True},
            )]})
            playwright.expect(card).to_contain_text("Next: await_human_approval")
            page.get_by_role("button", name="Refresh", exact=True).click()
            next_held_review().fulfill(json={"reviews": [review(
                "green", "verified_integrated", "retirement_eligible",
                {"generation": 1, "verified": True},
            )]})
            playwright.expect(card).to_contain_text("verified_integrated")
            assert all(request.request.method == "POST" for request in posts)
        finally:
            browser.close()


def test_epic_lifecycle_buttons_reconcile_in_real_browser(ui_server):
    """Exercise actual board DOM with delayed writes and intervening poll responses."""
    playwright = pytest.importorskip("playwright.sync_api")
    base, _root = ui_server
    with urllib.request.urlopen(base + "/api/board") as response:
        board = json.load(response)

    epic = next(row for row in board["epics"]["1_backlog"] if row["id"] == "epic_001")
    writes = []
    reads = []
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium unavailable: {exc}")
        try:
            page = browser.new_page()

            def read_board(route):
                reads.append(route.request.url)
                route.fulfill(json=board)

            def hold_write(route):
                writes.append(route)

            def wait_for_poll():
                previous = len(reads)
                for _ in range(60):
                    page.wait_for_timeout(200)
                    if len(reads) > previous:
                        # Allow the delivered response to reach the render callback.
                        page.wait_for_timeout(100)
                        return
                pytest.fail("no board poll completed")

            page.route("**/api/board?*", read_board)
            page.route("**/api/activate_epic", hold_write)
            page.route("**/api/approve_epic_plan", hold_write)
            page.goto(base)
            row = page.locator('.board-row[data-id="epic_001"]')
            activate = row.get_by_role("button", name="Activate team", exact=True)
            playwright.expect(activate).to_be_enabled(timeout=15000)

            # A poll completing while the pointer is held must not swallow the click.
            activate.hover()
            page.mouse.down()
            wait_for_poll()
            page.mouse.up()
            playwright.expect(row.get_by_role("button", name="Activating…")).to_be_disabled()
            assert len(writes) == 1
            wait_for_poll()
            playwright.expect(row.get_by_role("button", name="Activating…")).to_be_disabled()
            assert len(writes) == 1

            # A refused activation stays visible on the affected row after polling.
            refusal = "Existing checkout contains work; activation was refused."
            writes[0].fulfill(json={"ok": False, "reason": "existing_activation_run", "message": refusal})
            feedback = row.locator(".lifecycle-action-feedback")
            playwright.expect(feedback).to_have_text(refusal)
            wait_for_poll()
            playwright.expect(feedback).to_have_text(refusal)
            playwright.expect(activate).to_be_enabled()
            activate.click()
            playwright.expect(row.get_by_role("button", name="Activating…")).to_be_disabled()
            playwright.expect(feedback).to_have_count(0)
            assert len(writes) == 2

            # Acknowledgement is visible before the full board has caught up.
            writes[1].fulfill(json={"ok": True})
            playwright.expect(row.get_by_role("button", name="Activated — refreshing…")).to_be_disabled()
            board["epics"]["1_backlog"].remove(epic)
            epic.update(status="active", plan_readiness={"status": "ready_for_review", "can_approve_plan": True})
            board["epics"]["2_active"].append(epic)
            active_row = page.locator('[data-tier="epics"] [data-column="2_active"] .board-row[data-id="epic_001"]')
            approve = active_row.get_by_role("button", name="Approve plan", exact=True)
            playwright.expect(approve).to_be_enabled(timeout=15000)
            approve.click()
            playwright.expect(active_row.get_by_role("button", name="Approving…")).to_be_disabled()
            assert len(writes) == 3
            wait_for_poll()
            playwright.expect(active_row.get_by_role("button", name="Approving…")).to_be_disabled()
            assert len(writes) == 3
            writes[2].fulfill(json={"ok": True})
            playwright.expect(active_row.get_by_role("button", name="Approved — refreshing…")).to_be_disabled()
            epic["plan_approved"] = True
            playwright.expect(active_row.get_by_role("button", name="Approved", exact=True)).to_be_disabled(timeout=15000)
            assert len(writes) == 3
        finally:
            browser.close()
