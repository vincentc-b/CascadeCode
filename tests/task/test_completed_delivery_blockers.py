"""Completed delivery reconciles historical supervisor blockers after restart."""
from pathlib import Path

import pytest

from cascade.board.store import move_doc, read_doc, write_doc
from cascade.feature.recovery import recovery_status
from cascade.task.action_recovery import load_action, reconcile_completed_task_delivery
from cascade.task.supervisor_recovery import RecoveryResult, _write_ledger, recovery_incident
from cascade.task_rollup import _clear_delivery_blockers, invalidate_task_merge, queue_task_merge
from cascade.watchdog.blockage import propagate_direct_report_blockage
from cascade.watchdog.health import clear_health_memory, sweep_supervisor_health
from tests.support import add_doc, make_repo


def prepared(tmp_path: Path, *, manual=False, unrelated=False):
    root = make_repo(tmp_path)
    add_doc(root, id='epic_001', title='Epic', tier='epic', status='active')
    add_doc(root, id='feat_001', title='Feature', tier='feature', status='active', parent='epic_001')
    add_doc(root, id='task_001', title='Task', tier='task', status='active', parent='feat_001')
    feature = read_doc('feat_001', root=root)
    feature.meta.children = ['task_001']
    if manual:
        feature.meta.status = 'blocked'
    write_doc(feature, root=root)
    incident_id = 'task_001:delivery:1:0123456789abcdef01234567'
    incident = RecoveryResult(incident_id, 'already_delivered', 'validated_delivery_already_queued', False, 1)
    _write_ledger(root, {incident_id: incident.as_dict()})
    task = read_doc('task_001', root=root)
    propagate_direct_report_blockage(read_doc('feat_001', root=root), task,
        'task_not_recoverable', root=root, incident_id=incident_id)
    if unrelated:
        # Even a similarly shaped ID must not be cleared without ledger provenance.
        propagate_direct_report_blockage(read_doc('feat_001', root=root), task,
            'separate review hold', root=root, incident_id='task_001:delivery:1:unrecorded')
    queue_task_merge('task_001', root=root)
    return root, incident_id


@pytest.mark.parametrize('cleanup', ['merge', 'restart_sweep'])
@pytest.mark.parametrize('retained', ['none', 'manual', 'unrelated'])
def test_completed_delivery_clears_only_recorded_blockers(tmp_path, monkeypatch, cleanup, retained):
    root, incident_id = prepared(tmp_path, manual=retained == 'manual', unrelated=retained == 'unrelated')
    move_doc('task_001', 'completed', root=root)
    reconcile_completed_task_delivery('task_001', root=root)
    invalidate_task_merge('task_001', root=root)
    assert load_action('task_001:queued_merge', root=root)['recovery_state'] == 'completed'
    ledger = root / '.cascade/orphan_delivery_recoveries.json'
    before = ledger.read_bytes()
    monkeypatch.setattr('cascade.boss.merge.merge_task_branch',
                        lambda *a, **k: pytest.fail('completed Task must not merge again'))
    clear_health_memory()
    for _ in range(2):
        if cleanup == 'merge':
            _clear_delivery_blockers('task_001', root)
        else:
            sweep_supervisor_health(root)
    feature = read_doc('feat_001', root=root)
    assert all(b.incident_id != incident_id for b in feature.meta.monitoring_blockers)
    assert feature.meta.status == ('active' if retained == 'none' else 'blocked')
    assert len(feature.meta.monitoring_blockers) == (1 if retained == 'unrelated' else 0)
    assert ledger.read_bytes() == before
    result = recovery_incident('task_001', root=root)
    assert result.decision == 'already_delivered'
    assert result.reason == 'task_completed'
    view = recovery_status('task_001', feature_id='feat_001', root=root)
    assert view['phase'] == 'completed'
    assert view['action'] == 'none'
    assert 'continue Feature planning' in view['next_safe_step']


def test_empty_queue_does_not_clear_a_live_task_incident(tmp_path):
    root, incident_id = prepared(tmp_path)
    invalidate_task_merge('task_001', root=root)
    assert recovery_incident('task_001', root=root).reason == 'delivery_invalidated_revalidation_pending'
    sweep_supervisor_health(root)
    feature = read_doc('feat_001', root=root)
    assert feature.meta.status == 'blocked'
    assert any(b.incident_id == incident_id for b in feature.meta.monitoring_blockers)


def test_recovered_planning_gets_a_turn_before_automatic_closeout(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from cascade.boss.rollup import _delivery_recovery_planning_pending, _rollup_gates_pass
    from cascade.board.store import list_board
    from cascade.watchdog.events import read_events

    root, _ = prepared(tmp_path)
    move_doc('task_001', 'completed', root=root)
    _clear_delivery_blockers('task_001', root)
    _clear_delivery_blockers('task_001', root)
    events, end = read_events('feat_001', 0, root=root)
    assert sum(e.type == 'TaskDeliveryBlockageCleared' for e in events) == 1
    state = SimpleNamespace(values={'last_queue_offset': 0}, next=())
    monkeypatch.setattr('cascade.feature.graph.ensure_feature_graph',
                        lambda *a, **k: SimpleNamespace(get_state=lambda config: state))
    monkeypatch.setattr('cascade.workspace.kickoff.graph_turn_owner_is_live', lambda _: False)
    assert _delivery_recovery_planning_pending('feat_001', root)
    assert not _rollup_gates_pass('feat_001', '## Closeout\n\nDone.\n', list_board(root), root)
    state.values['last_queue_offset'] = end
    state.next = ('lead',)
    assert _delivery_recovery_planning_pending('feat_001', root)
    state.next = ()
    monkeypatch.setattr('cascade.workspace.kickoff.graph_turn_owner_is_live', lambda _: True)
    assert _delivery_recovery_planning_pending('feat_001', root)
    monkeypatch.setattr('cascade.workspace.kickoff.graph_turn_owner_is_live', lambda _: False)
    assert not _delivery_recovery_planning_pending('feat_001', root)
    assert _rollup_gates_pass('feat_001', '## Closeout\n\nDone.\n', list_board(root), root)
