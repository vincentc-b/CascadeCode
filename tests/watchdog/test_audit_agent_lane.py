from datetime import datetime, timezone
import json
from types import SimpleNamespace
import threading
import time

import pytest

from cascade.watchdog import audit_agent_lane as lane
from cascade.watchdog import audit_investigation as cases
from cascade.watchdog import audit_lane as scanner
from cascade.watchdog.events import read_events
from tests.watchdog.test_audit_investigation import board as fresh_board


def board(tmp_path):
    root = fresh_board(tmp_path)
    lane._write_json_atomically(lane._home(root) / "agent_activity.json", {
        "first_seen": {"epic_001": 0, "feat_001": 0, "task_001": 0}})
    return root


def test_periodic_reviews_are_independent_of_classifier_and_restart(tmp_path, monkeypatch):
    root = board(tmp_path)
    monkeypatch.setattr(scanner, 'project_audit_observation', lambda *a, **k: pytest.fail('scanner invoked'))
    lane.AuditInvestigationWorker(root, interval_seconds=60).run_once(now=11000)
    assert {c['owner_id'] for c in cases.read_investigation_cases(root=root)} == {'epic_001', 'feat_001'}
    lane.AuditInvestigationWorker(root, interval_seconds=60).run_once(now=11010)
    assert len(read_events('feat_001', 0, root=root)[0]) == 1
    lane.AuditInvestigationWorker(root, interval_seconds=60).run_once(now=11061)
    assert len(read_events('feat_001', 0, root=root)[0]) == 2


def test_failed_request_does_not_block_other_owner_and_retries(tmp_path, monkeypatch):
    root = board(tmp_path)
    worker = lane.AuditInvestigationWorker(root, enabled=False)
    lane.enqueue_investigations(root, tuple({'work_id': w, 'reason': 'unknown', 'evidence': {}} for w in ('feat_001', 'epic_001')))
    original = cases.request_investigation
    def fail(work_id, **kwargs):
        if work_id == 'feat_001':
            raise OSError('unavailable')
        return original(work_id, **kwargs)
    monkeypatch.setattr(cases, 'request_investigation', fail)
    worker.run_once(now=11000)
    assert len(read_events('epic_001', 0, root=root)[0]) == 1
    assert lane.investigation_schedule(root)['last_error']['delivery_failures']
    monkeypatch.setattr(cases, 'request_investigation', original)
    worker.run_once(now=11061)
    assert len(read_events('feat_001', 0, root=root)[0]) == 1
    assert not list((lane._home(root) / 'agent_outbox').glob('*.json'))


def test_disabled_reviews_allow_manual_request(tmp_path):
    root = board(tmp_path)
    worker = lane.AuditInvestigationWorker(root, enabled=False)
    worker.run_once(now=11000)
    assert not cases.read_investigation_cases(root=root)
    lane.request_agent_review(root)
    worker.run_once(now=11001)
    assert len(cases.read_investigation_cases(root=root)) == 2


def test_reported_fix_is_reassessed_at_cadence_with_prior_finding(tmp_path):
    root = board(tmp_path)
    worker = lane.AuditInvestigationWorker(root, interval_seconds=60)
    worker.run_once(now=11000)
    case = cases.request_investigation('task_001', 'unknown_failure', {}, root=root,
                                       now=datetime.fromtimestamp(11000, timezone.utc))
    cases.report_audit_investigation(case['case_id'], 'Removed obsolete blocker', 'reported_fixed',
                                    root=root, feature_id='feat_001', now=datetime.fromtimestamp(11001, timezone.utc))
    worker.run_once(now=11005)
    before = len(read_events('feat_001', 0, root=root)[0])
    worker.run_once(now=11061)
    events = read_events('feat_001', 0, root=root)[0]
    assert len(events) > before
    assert any('Removed obsolete blocker' in e.payload['body'] for e in events)
    assert next(c for c in cases.read_investigation_cases(root=root) if c['case_id'] == case['case_id'])['status'] != 'resolved'


def test_unknown_probe_exception_is_durable_investigation_input(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, 'select_audit_candidates', lambda *a, **k: SimpleNamespace(
        candidates=(SimpleNamespace(work_id='feat_001', tier='feature', evidence_available=True),),
        next_cursor='next', unavailable_evidence=(), continuation_cursors=('next',)))
    def unknown(*a, **k):
        raise RuntimeError('sensitive details not copied')
    monkeypatch.setattr(scanner, 'project_audit_observation', unknown)
    result = scanner._run_bounded_audit_pass_inline(tmp_path, None, threading.Event(),
                                                   max_items=10, max_seconds=60, monotonic=time.monotonic)
    assert result.next_cursor == 'next'
    assert result.investigation_requests[0]['reason'] == 'audit_observation_error'
    assert 'sensitive' not in json.dumps(result.investigation_requests)


@pytest.mark.parametrize('tier,owner,role', [('epic', 'epic_001', 'epic_manager'), ('feature', 'feat_001', 'feature_lead')])
def test_agent_mcp_report_is_exposed_and_scoped(tmp_path, tier, owner, role):
    from cascade.agent.mcp_wrappers import dispatch_planning_tool, ToolEffectCollector
    from cascade.epic.wiring import load_epic_tools
    from cascade.feature.wiring import load_feature_tools
    from cascade.epic.registry import epic_tools
    from cascade.feature.registry import feature_tools
    root = board(tmp_path)
    load_epic_tools()
    load_feature_tools()
    assert 'report_audit_investigation' in epic_tools()
    assert 'report_audit_investigation' in feature_tools()
    case = cases.request_investigation(owner, 'periodic_agent_review', {}, root=root)
    args = {'case_id': case['case_id'], 'finding': 'Waiting on live child; no duplicate work', 'outcome': 'waiting'}
    result = dispatch_planning_tool(tier, 'report_audit_investigation', args, scope_id=owner,
                                   repo_root=root, collector=ToolEffectCollector(), role=role)
    assert result['latest_outcome'] == 'waiting'
    with pytest.raises(PermissionError):
        dispatch_planning_tool(tier, 'report_audit_investigation', {**args, 'root': '/tmp'},
                               scope_id=owner, repo_root=root, collector=ToolEffectCollector(), role=role)


def test_failed_periodic_scan_and_corrupt_envelope_do_not_starve_delivery(tmp_path, monkeypatch):
    root = board(tmp_path)
    worker = lane.AuditInvestigationWorker(root)
    def broken(*a, **k):
        raise RuntimeError('scan failed')
    monkeypatch.setattr(worker, '_schedule_owner_reviews', broken)
    lane.enqueue_investigations(root, ({'work_id': 'feat_001', 'reason': 'unknown', 'evidence': {}},))
    (lane._home(root) / 'agent_outbox' / '0-corrupt.json').write_text('{')
    worker.run_once(now=11000)
    assert len(read_events('feat_001', 0, root=root)[0]) == 1
    assert lane.investigation_schedule(root)['last_error']


def test_new_work_waits_twenty_minutes_across_restart_including_outbox(tmp_path):
    root = fresh_board(tmp_path)
    lane.enqueue_investigations(root, ({'work_id': 'task_001', 'reason': 'audit_observation_error', 'evidence': {}},))
    worker = lane.AuditInvestigationWorker(root, interval_seconds=60)
    worker.run_once(now=10000)
    assert not cases.read_investigation_cases(root=root)
    lane.AuditInvestigationWorker(root, interval_seconds=60).run_once(now=11199)
    assert not cases.read_investigation_cases(root=root)
    lane.AuditInvestigationWorker(root, interval_seconds=60).run_once(now=11260)
    assert len(read_events('feat_001', 0, root=root)[0]) >= 1
    assert lane.investigation_schedule(root)['admission']['ready']


def test_idle_workspace_never_dispatches_even_with_manual_or_queued_work(tmp_path, monkeypatch):
    from tests.support import make_repo
    root = make_repo(tmp_path, git=False)
    lane.enqueue_investigations(root, ({'work_id': 'epic_old', 'reason': 'audit_observation_error', 'evidence': {}},))
    lane.request_agent_review(root)
    monkeypatch.setattr(cases, 'request_investigation', lambda **k: pytest.fail('idle dispatch'))
    monkeypatch.setattr(cases, 'replay_pending_investigations', lambda **k: pytest.fail('idle replay'))
    lane.AuditInvestigationWorker(root).run_once(now=10000)
    assert lane.investigation_schedule(root)['admission']['reason'] == 'no_live_work'
    assert not cases.read_investigation_cases(root=root)


def test_oldest_live_item_qualifies_and_retired_age_is_removed(tmp_path):
    root = fresh_board(tmp_path)
    path = lane._home(root) / 'agent_activity.json'
    lane._write_json_atomically(path, {'first_seen': {'epic_retired': 0, 'task_001': 8800}})
    result = lane._agent_admission(root, 10000)
    assert result['ready'] and result['oldest_age_seconds'] == 1200
    assert 'epic_retired' not in result['first_seen']
    assert result['first_seen']['epic_001'] == 10000


def test_manual_review_bypasses_grace_for_live_work(tmp_path):
    root = fresh_board(tmp_path)
    lane.request_agent_review(root)
    lane.AuditInvestigationWorker(root).run_once(now=10000)
    assert len(cases.read_investigation_cases(root=root)) == 2
