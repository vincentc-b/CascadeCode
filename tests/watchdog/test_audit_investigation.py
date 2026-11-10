from datetime import datetime, timedelta, timezone
import json
from threading import Thread

import pytest

from cascade.board.context import set_project_context
from cascade.watchdog import audit_investigation as module
from cascade.watchdog.events import read_events
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def board(tmp_path, *, completed_feature=False, completed_epic=False):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed" if completed_epic else "active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001", status="completed" if completed_feature else "active")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001", status="blocked")
    return root


def request(root, **kwargs):
    return module.request_investigation("task_001", "unknown_failure", {"status": "blocked", "errors": ["unrecognized_adapter"]}, root=root, now=NOW, **kwargs)


def test_routes_task_to_feature_and_keeps_case_open_after_enqueue(tmp_path):
    root = board(tmp_path)
    result = request(root)
    events, _ = read_events("feat_001", 0, root=root)
    assert len(events) == 1 and events[0].type == "TeamMessage"
    assert events[0].payload["case_id"] == result["case_id"]
    assert result["status"] == "delivered"
    assert "report_audit_investigation" in events[0].payload["body"]
    assert "Do not rewrite main" in events[0].payload["body"]
    assert module.read_investigation_cases(root=root)[0]["status"] != "resolved"
    assert not list(root.rglob("*.sqlite"))  # No model graph is synchronously started.


@pytest.mark.parametrize("work_id", ["feat_001", "epic_001"])
def test_parent_teams_receive_their_own_periodic_review(tmp_path, work_id):
    root = board(tmp_path)
    result = module.request_investigation(work_id, "periodic_agent_review", {"classification": "healthy"}, root=root, now=NOW)
    assert result["owner_id"] == work_id
    assert len(read_events(work_id, 0, root=root)[0]) == 1


def test_material_evidence_and_cooldown_control_repeated_delivery(tmp_path):
    root = board(tmp_path)
    first = request(root)
    assert request(root)["deduplicated"]
    same = module.request_investigation("task_001", "unknown_failure", {
        "status": "blocked", "errors": ["unrecognized_adapter"], "timestamp": "changed", "prompt": "ignored",
    }, root=root, now=NOW + timedelta(seconds=10))
    assert same["deduplicated"]
    changed = module.request_investigation("task_001", "unknown_failure", {"status": "blocked", "errors": ["new_error"]}, root=root, now=NOW + timedelta(seconds=11))
    assert changed["case_id"] == first["case_id"]
    assert changed["delivery_generation"] == 2
    after = module.request_investigation("task_001", "unknown_failure", {"status": "blocked", "errors": ["new_error"]}, root=root, now=NOW + timedelta(hours=1))
    assert after["delivery_generation"] == 3
    assert len(read_events("feat_001", 0, root=root)[0]) == 3


def test_replay_after_append_crash_does_not_duplicate_retained_message(tmp_path, monkeypatch):
    root = board(tmp_path)
    original = module._write
    def crash(path, case):
        if case["status"] == "delivered":
            raise SystemExit("crash after append")
        original(path, case)
    monkeypatch.setattr(module, "_write", crash)
    with pytest.raises(SystemExit):
        request(root)
    assert module.read_investigation_cases(root=root)[0]["status"] == "queued"
    assert len(read_events("feat_001", 0, root=root)[0]) == 1
    monkeypatch.setattr(module, "_write", original)
    recovered = module.replay_pending_investigations(root=root, now=NOW)
    assert recovered[0]["status"] == "delivered"
    assert len(read_events("feat_001", 0, root=root)[0]) == 1
    assert not module.replay_pending_investigations(root=root)


def test_replay_of_delivery_failure_retains_case_and_error(tmp_path, monkeypatch):
    root = board(tmp_path)
    original = module.append_event
    monkeypatch.setattr(module, "append_event", lambda *a, **k: (_ for _ in ()).throw(OSError("secret token=never-copy")))
    with pytest.raises(OSError):
        request(root)
    case = module.read_investigation_cases(root=root)[0]
    assert case["status"] == "queued" and case["delivery_error"] == "OSError"
    assert "never-copy" not in json.dumps(case)
    monkeypatch.setattr(module, "append_event", original)
    assert module.replay_pending_investigations(root=root)[0]["status"] == "delivered"


def test_redacted_allowlisted_bounded_evidence(tmp_path):
    root = board(tmp_path)
    evidence = {
        "prompt": "private prompt", "thinking": "private reasoning", "raw_log": "private log",
        "errors": ["token=token-secret password=pw-secret Bearer bearer-secret https://u:p@host/path?access_token=url-secret"],
        "events": [{"type": "Failure", "payload": {"prompt": "private-provider-content"}, "code": "exit"}],
        "child_statuses": {"task_001": "blocked"},
    }
    result = module.request_investigation("epic_001", "periodic_agent_review", evidence, root=root, now=NOW)
    raw = json.dumps(result) + json.dumps([e.payload for e in read_events("epic_001", 0, root=root)[0]])
    for secret in ["private prompt", "private reasoning", "private log", "private-provider-content", "token-secret", "pw-secret", "bearer-secret", "url-secret", "u:p@"]:
        assert secret not in raw
    assert result["evidence"]["child_statuses"] == {"task_001": "blocked"}
    huge = module.request_investigation("epic_001", "huge_evidence", {"events": [{"errors": ["x" * 5000] * 12}] * 12}, root=root)
    assert len(json.dumps(huge).encode()) < module._MAX_FILE


def test_split_roots_store_cases_in_tracking_and_queue_in_product(tmp_path):
    tracking = board(tmp_path / "tracking")
    product = make_repo(tmp_path / "product", git=False)
    set_project_context(ProjectContext.split(product, tracking))
    try:
        result = request(product)
        assert (tracking / ".cascade/audit_investigations" / (result["case_id"] + ".json")).exists()
        assert len(read_events("feat_001", 0, root=product)[0]) == 1
        assert not (tracking / "docs/_queue/feat_001.jsonl").exists()
        assert module.read_investigation_cases(root=tracking)[0]["case_id"] == result["case_id"]
    finally:
        set_project_context(None)


def test_reports_are_owner_scoped_and_fixed_is_only_a_reassessment(tmp_path):
    root = board(tmp_path)
    case = request(root)
    with pytest.raises(PermissionError):
        module.report_audit_investigation(case["case_id"], "I fixed it", "reported_fixed", root=root, epic_id="epic_001", now=NOW)
    reported = module.report_audit_investigation(case["case_id"], "PR tests passed; awaiting canonical verification", "reported_fixed", {"status": "fixed"}, ["https://forge/pull/123"], root=root, feature_id="feat_001", now=NOW)
    assert reported["status"] == "reassess"
    assert reported["latest_outcome"] == "reported_fixed"
    assert reported["next_reassessment_at"] == NOW.isoformat()
    fresh = request(root)
    assert fresh["delivery_generation"] == 2
    assert fresh["reports"][0]["outcome"] == "reported_fixed"
    with pytest.raises(ValueError):
        module.report_audit_investigation(case["case_id"], "done", "resolved", root=root, feature_id="feat_001")


def test_retired_feature_escalates_and_retired_epic_is_not_awakened(tmp_path):
    root = board(tmp_path, completed_feature=True)
    assert request(root)["owner_id"] == "epic_001"
    assert len(read_events("epic_001", 0, root=root)[0]) == 1
    retired = board(tmp_path / "retired", completed_feature=True, completed_epic=True)
    result = request(retired)
    assert result["status"] == "reassess"
    assert result["delivery_error"] == "owning_team_retired"
    assert not (retired / "docs/_queue").exists()


def test_concurrent_identical_requests_coalesce(tmp_path):
    root = board(tmp_path)
    results = []
    workers = [Thread(target=lambda: results.append(request(root))) for _ in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(5)
    assert len(results) == 3
    assert sum(not r["deduplicated"] for r in results) == 1
    assert len(read_events("feat_001", 0, root=root)[0]) == 1


def test_missing_read_is_silent_and_malformed_record_fails_closed(tmp_path):
    root = board(tmp_path)
    before = set(root.rglob("*"))
    assert module.read_investigation_cases(root=root) == ()
    assert set(root.rglob("*")) == before
    case = request(root)
    module._case_path(root, case["case_id"]).write_text("{")
    with pytest.raises(module.InvestigationUnavailable):
        module.read_investigation_cases(root=root)


def test_incomplete_queue_never_claims_delivered(tmp_path):
    root = board(tmp_path)
    queue = root / "docs/_queue/feat_001.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text('{"partial":')
    with pytest.raises(module.InvestigationUnavailable, match="incomplete"):
        request(root)
    assert module.read_investigation_cases(root=root)[0]["status"] == "queued"
    assert queue.read_text() == '{"partial":'


def test_reports_stay_bounded_across_repeated_large_progress_updates(tmp_path):
    root = board(tmp_path)
    case = request(root)
    for _ in range(12):
        result = module.report_audit_investigation(case["case_id"], "f" * 20000, "waiting",
            {"errors": ["e" * 20000] * 20}, ["p" * 20000] * 20,
            root=root, feature_id="feat_001")
    assert len(result["reports"]) == 8
    assert module._case_path(root, case["case_id"]).stat().st_size < module._MAX_FILE


def test_replay_failed_case_does_not_starve_other_owners(tmp_path, monkeypatch):
    root = board(tmp_path)
    original = module.append_event
    monkeypatch.setattr(module, "append_event", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        request(root)
    with pytest.raises(OSError):
        module.request_investigation("epic_001", "periodic_agent_review", {}, root=root, now=NOW)
    monkeypatch.setattr(module, "append_event", original)
    queue = root / "docs/_queue/feat_001.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_bytes(b" " * (module._MAX_QUEUE_SCAN + 1) + b"\n")
    results = module.replay_pending_investigations(root=root)
    assert {row["status"] for row in results} == {"queued", "delivered"}
    assert len(read_events("epic_001", 0, root=root)[0]) == 1
    assert queue.stat().st_size == module._MAX_QUEUE_SCAN + 2


def _hold_case_lock(path, ready, release):
    with module._locked(path):
        ready.set()
        release.wait(5)


def test_case_lock_is_bounded_across_processes(tmp_path):
    import multiprocessing
    root = board(tmp_path)
    case = request(root)
    path = module._case_path(root, case["case_id"])
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    process = context.Process(target=_hold_case_lock, args=(path, ready, release))
    process.start()
    try:
        assert ready.wait(10)
        with pytest.raises(module.InvestigationUnavailable, match="lock busy"):
            request(root)
    finally:
        release.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert process.exitcode == 0
    assert len(read_events("feat_001", 0, root=root)[0]) == 1
