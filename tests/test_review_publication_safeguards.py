from dataclasses import replace
from pathlib import Path
import os
import subprocess
import sys
import time

import pytest

from cascade import review_rebase
from cascade.review_owner import current_review_owner, review_owner_exited
from cascade.review_validation import run_review_validation, review_validation_timeout
from cascade.validation_command import review_validation_command
from cascade.task import action_recovery as actions
from cascade.watchdog.events import read_events
from tests.test_review_rebase import _execution_ready_turn, _git
from tests.support import make_repo, add_doc


def test_review_validation_selects_changed_and_adjacent_tests(tmp_path):
    for name in (
        "tests/test_review_rebase.py",
        "tests/test_review_publication_safeguards.py",
        "tests/workspace/test_architecture_review.py",
        "tests/war_room/test_http_read.py",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    command = review_validation_command(
        tmp_path,
        tmp_path,
        (
            "cascade/workspace/architecture_review.py",
            "tests/war_room/test_http_read.py",
            "docs/epics/3_completed/epic_045.md",
            "tests/../outside.py",
        ),
    )

    assert command == (
        "python3", "-m", "pytest", "-q",
        "tests/test_review_publication_safeguards.py",
        "tests/test_review_rebase.py",
        "tests/war_room/test_http_read.py",
        "tests/workspace/test_architecture_review.py",
    )


def test_review_validation_respects_explicit_repository_command(tmp_path):
    (tmp_path / "cascade.toml").write_text(
        '[validation]\ncommand = ["python3", "-m", "pytest", "-q"]\n',
        encoding="utf-8",
    )
    assert review_validation_command(
        tmp_path, tmp_path, ("tests/war_room/test_http_read.py",)
    ) == ("python3", "-m", "pytest", "-q")


def test_duplicate_lifecycle_document_blocks_before_checks_and_push(tmp_path, monkeypatch):
    root, turn = _execution_ready_turn(tmp_path)
    execution = review_rebase.execute_review_rebase(turn, authorized_paths=('source.txt',))
    original = next(root.glob('docs/features/**/*.md'))
    duplicate = root / 'docs/features/3_completed' / original.name
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    duplicate.write_text(original.read_text())
    _git(root, 'add', 'docs')
    _git(root, 'commit', '-m', 'simulate duplicate after conflict resolution')
    execution = replace(execution, source_head=_git(root, 'rev-parse', 'HEAD'))
    monkeypatch.setattr(review_rebase, 'run_review_validation', lambda *a, **k: pytest.fail('checks must not run'))
    result = review_rebase.check_and_publish_review_rebase(turn, execution)
    assert not result.published
    assert result.blocker.code == 'board_validation_failed'
    assert _git(root, 'ls-remote', 'origin', f'refs/heads/{turn.source_ref}').split()[0] == turn.observed_source_sha
    assert duplicate.exists()  # Never guess which document should be removed.


def test_timeout_is_typed_and_never_pushes(tmp_path, monkeypatch):
    root, turn = _execution_ready_turn(tmp_path)
    execution = review_rebase.execute_review_rebase(turn, authorized_paths=('source.txt',))
    monkeypatch.setattr(review_rebase, 'validation_command', lambda r: (sys.executable, '-c', 'import time; time.sleep(30)'))
    monkeypatch.setattr(review_rebase, 'review_validation_timeout', lambda r: .1)
    result = review_rebase.check_and_publish_review_rebase(turn, execution)
    assert result.blocker.code == 'repository_checks_timed_out'
    assert _git(root, 'ls-remote', 'origin', f'refs/heads/{turn.source_ref}').split()[0] == turn.observed_source_sha


def test_timeout_stops_validation_descendants(tmp_path):
    script = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); pathlib.Path('child.pid').write_text(str(p.pid)); time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_review_validation((sys.executable, '-c', script), cwd=tmp_path, timeout=1)
    pid = int((tmp_path / 'child.pid').read_text())
    stat = Path(f'/proc/{pid}/stat')
    # SIGKILL delivery and descendant teardown can lag the reaped group leader.
    # Still fail if a child survives the bounded scheduler allowance.
    deadline = time.monotonic() + 1
    while True:
        try:
            state = stat.read_text().split(') ')[1].split()[0]
        except FileNotFoundError:
            break
        if state == 'Z':
            break
        assert time.monotonic() < deadline, f'validation descendant still {state}'
        time.sleep(0.01)


def test_validation_output_is_bounded(tmp_path):
    result = run_review_validation((sys.executable, '-c', "print('x'*100000)"), cwd=tmp_path, timeout=5)
    assert result.returncode == 0 and len(result.stdout) == 65536


@pytest.mark.parametrize('value', ['true', '0', '3601', '"unbounded"'])
def test_invalid_timeout_config_rejected(tmp_path, value):
    (tmp_path / 'cascade.toml').write_text('[validation]\nreview_timeout_seconds = '+value+'\n')
    with pytest.raises(ValueError):
        review_validation_timeout(tmp_path)


def test_killed_publication_owner_is_returned_to_team_exactly_once(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id='epic_001', title='Epic', tier='epic', status='completed')
    actions.create_or_load_action('publication:test', 'review_rebase', root=root, attempt_bound=3,
        owning_team={'kind': 'epic_team', 'work_id': 'epic_001'})
    code = '''import cascade.board
from pathlib import Path
import os,sys
from cascade.task.action_recovery import resume_action
resume_action('publication:test', root=Path(sys.argv[1]), execute=lambda ctx: os._exit(9))
'''
    child = subprocess.run([sys.executable, '-c', code, str(root)])
    assert child.returncode == 9
    before = actions.load_action('publication:test', root=root)
    assert before['recovery_state'] == 'running'
    assert before['execution_claim']['owner_process']['pid'] > 0
    assert actions.reconcile_abandoned_review_publications(root=root) == 1
    assert actions.reconcile_abandoned_review_publications(root=root) == 0
    after = actions.load_action('publication:test', root=root)
    assert after['recovery_state'] == 'awaiting_owner_decision'
    assert 'execution_claim' not in after
    assert after['attempts'][-1]['completion_metadata']['reason'] == 'publication_owner_exited'
    events, _ = read_events('epic_001', 0, root=root)
    assert len(events) == 1 and events[0].type == 'BranchActionRecoveryRequested'
    assert 'epic_001' in actions.pending_recovery_team_ids(root=root)


def test_live_claim_is_not_reclaimed_due_to_age_and_legacy_is_not_guessed(tmp_path):
    root = make_repo(tmp_path, git=False)
    actions.create_or_load_action('publication:live', 'review_rebase', root=root, attempt_bound=3)
    actions._claim_resume_attempt('publication:live', root=root)
    assert actions.reconcile_abandoned_review_publications(root=root) == 0
    assert actions.load_action('publication:live', root=root)['recovery_state'] == 'running'
    assert not review_owner_exited(None)
    assert not review_owner_exited({'pid': os.getpid()})
    assert not review_owner_exited(current_review_owner())
    reused = {**current_review_owner(), 'start_ticks': 'different'}
    assert review_owner_exited(reused)


def test_unknown_process_evidence_never_reclaims(monkeypatch):
    import cascade.review_owner as module
    owner = current_review_owner()
    def denied(pid):
        raise PermissionError('unreadable process')
    monkeypatch.setattr(module, 'process_identity', denied)
    assert not module.review_owner_exited(owner)


def test_validation_scans_physical_checkout_in_split_session(tmp_path):
    from cascade.board.context import set_project_context
    from cascade.workspace.types import ProjectContext
    from cascade.review_validation import validate_publication_board
    from cascade.board.errors import SchemaError
    product = make_repo(tmp_path / 'product', git=False)
    tracking = make_repo(tmp_path / 'tracking', git=False)
    add_doc(product, id='epic_001', title='Epic', tier='epic', status='active')
    add_doc(product, id='feat_001', title='Feature', tier='feature', status='backlog', parent='epic_001')
    original = next(product.glob('docs/features/1_backlog/*.md'))
    duplicate = product / 'docs/features/3_completed' / original.name
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    duplicate.write_text(original.read_text())
    set_project_context(ProjectContext.split(product, tracking))
    try:
        with pytest.raises(SchemaError):
            validate_publication_board(product)
    finally:
        set_project_context(None)


def test_malformed_board_document_is_not_silently_omitted(tmp_path):
    from cascade.review_validation import validate_publication_board
    from cascade.board.errors import SchemaError
    path = tmp_path / 'docs/features/1_backlog/feat_001_broken.md'
    path.parent.mkdir(parents=True)
    path.write_text('---\nid: feat_001\n---\nIncomplete work document')
    with pytest.raises(SchemaError):
        validate_publication_board(tmp_path)


def test_repeated_failed_owner_publication_can_be_resolved_again(tmp_path, monkeypatch):
    from cascade.feature.review_recovery import publish_review_resolution
    root, turn = _execution_ready_turn(tmp_path)
    (root / '.git/info/exclude').write_text('.cascade/\ndocs/_queue/\n')
    _git(root, 'merge', 'epic/epic_035', '--no-edit')
    monkeypatch.setattr(review_rebase, 'validation_command', lambda r: (sys.executable, '-c', 'raise SystemExit(1)'))
    for attempt in (1, 2):
        result = publish_review_resolution(turn.action_id, feature_id='feat_035_001', root=root)
        assert result['recovery_state'] == 'awaiting_owner_decision'
        assert actions.load_action(turn.action_id, root=root)['attempt_count'] == attempt
    monkeypatch.setattr(review_rebase, 'validation_command', lambda r: (sys.executable, '-c', ''))
    result = publish_review_resolution(turn.action_id, feature_id='feat_035_001', root=root)
    assert result['recovery_state'] == 'completed'
    assert actions.load_action(turn.action_id, root=root)['attempt_count'] == 3


def test_dead_claim_check_precedes_failing_board_projection(tmp_path, monkeypatch):
    import cascade.automation
    import cascade.watchdog.loop as loop
    calls = []
    monkeypatch.setattr(actions, 'reconcile_abandoned_review_publications', lambda **k: calls.append('reconcile'))
    monkeypatch.setattr(cascade.automation, 'maybe_sync_briefs', lambda r: None)
    def invalid(root):
        calls.append('board')
        raise ValueError('duplicate document')
    monkeypatch.setattr(loop, '_tick_scan_active', invalid)
    with pytest.raises(ValueError):
        loop.watchdog_tick(root=tmp_path)
    assert calls == ['reconcile', 'board']
