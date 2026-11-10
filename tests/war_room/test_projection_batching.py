"""Board response sidecars are read once, without cross-request caching."""

from types import SimpleNamespace

from cascade import review
from cascade.war_room.recovery_incident import recovery_incidents_by_work_id


def test_completed_epic_staging_reads_registry_once(tmp_path, monkeypatch):
    worktree = tmp_path / 'epic-worktree'
    metas = [SimpleNamespace(
        id=f'epic_{i:03}', tier='epic', status='completed',
        path=worktree / '3_completed' / f'epic_{i:03}.md',
    ) for i in range(30)]
    calls = []
    entries = [SimpleNamespace(kind='epic', work_id=metas[0].id, path=worktree)]
    monkeypatch.setattr(review, 'locate_trunk', lambda root: root)
    monkeypatch.setattr(review, 'load_registry', lambda root: calls.append(root) or entries)
    staged = review.epic_close_documents_staged(metas, root=tmp_path)
    assert calls == [tmp_path]
    assert staged == {meta.id: meta is metas[0] for meta in metas}
    # A second request must observe the new registry, not a cached result.
    entries.clear()
    assert not any(review.epic_close_documents_staged(metas, root=tmp_path).values())
    assert len(calls) == 2


def test_incident_projection_reuses_supplied_actions(tmp_path, monkeypatch):
    from cascade.task import action_recovery

    calls = []
    actions = [{
        'action_id': 'action-1', 'recovery_state': 'blocked',
        'recovery': {'evidence': {'affected_work_id': 'epic_001'}},
    }]
    monkeypatch.setattr(action_recovery, 'recovery_actions', lambda **kwargs: calls.append(1) or actions)
    expected = recovery_incidents_by_work_id(root=tmp_path)
    assert calls == [1]
    assert recovery_incidents_by_work_id(root=tmp_path, actions=actions) == expected
    assert recovery_incidents_by_work_id(root=tmp_path, actions=[]) == {}
    assert calls == [1]
    assert actions[0]['recovery']['evidence']['affected_work_id'] == 'epic_001'
