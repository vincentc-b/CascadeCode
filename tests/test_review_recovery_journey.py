"""Recovery must finish real checks and publication, not merely wake an owner."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from cascade.board import store as _board_store  # noqa: F401 - initialize wiring
from cascade.review_health import reconcile_open_review_health
from cascade.feature import invoke_tool as invoke_feature_tool, load_feature_tools
from cascade.task.action_recovery import (
    ActionFailure, create_or_load_action, load_action, record_owner_decision,
    record_owner_resolution, resume_action,
)
from cascade.validation_command import validation_command
from cascade.review_validation import review_validation_command
from cascade.task.incident_budget import read_incident_budget
from tests.test_review_rebase import _execution_ready_turn
from tests.test_review_health import _git, _conflicting_snapshot


def _policy(
    root,
    command,
    timeout,
    *,
    owner='repository_operator',
    profile='cascade.review-publication',
):
    (root / 'cascade.toml').write_text(
        '[validation]\nreview_command = ' + json.dumps(command) +
        f'\nreview_timeout_seconds = {timeout}\n' +
        'review_policy_owner = ' + json.dumps(owner) + '\n' +
        'review_profile_id = ' + json.dumps(profile) + '\n'
    )


def _monitor_in_new_process(root):
    # Fake only the external forge response. Git, validator subprocesses, action
    # claims, durable decisions, leases, and the bare remote are all real.
    code = '''
import sys
from pathlib import Path
from cascade.board import store
from cascade import review_health
review_health.detect_forge = lambda root: 'github'
review_health.merge_request_snapshot = lambda *a: {'state':'open', 'mergeability':'conflicting', 'comments':[]}
print(review_health.reconcile_open_review_health(Path(sys.argv[1])))
'''
    source = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(source))
    return subprocess.run([sys.executable, '-c', code, str(root)], cwd=source,
                          env=env, capture_output=True, text=True, check=True)


def _resolved_review(tmp_path, monkeypatch):
    from cascade import review_health

    root, turn = _execution_ready_turn(tmp_path)
    # In this single-checkout fixture, ignored config models operator policy
    # outside the owned source line, as in a real trunk/integration checkout.
    (root / '.git/info/exclude').write_text('.cascade/\ndocs/_queue/\ncascade.toml\n')
    _git(root, 'merge', 'epic/epic_035', '--no-edit')
    monkeypatch.setattr(review_health, 'detect_forge', lambda root: 'github')
    monkeypatch.setattr(review_health, 'merge_request_snapshot', _conflicting_snapshot)
    return root, turn


def test_timed_out_recovery_waits_across_restart_then_publishes_after_policy_fix(tmp_path, monkeypatch):
    root, turn = _resolved_review(tmp_path, monkeypatch)
    head = _git(root, 'rev-parse', 'HEAD')
    pushes = tmp_path / 'publication-pushes.jsonl'
    remote = Path(_git(root, 'remote', 'get-url', 'origin'))
    hook = remote / 'hooks' / 'post-receive'
    hook.write_text(
        '#!/bin/sh\nwhile read old new ref; do '
        f'printf "%s %s %s\\n" "$old" "$new" "$ref" >> "{pushes}"; '
        'done\n'
    )
    hook.chmod(0o755)
    calls = tmp_path / 'validator-calls.jsonl'
    validator = tmp_path / 'validate_resolution.py'
    validator.write_text('''
import json, pathlib, subprocess, sys, time
root, log = map(pathlib.Path, sys.argv[1:])
assert (root / 'source.txt').read_text().strip() == 'source'
assert (root / 'target.txt').read_text().strip() == 'target'
if not log.exists():
    marker = log.with_suffix('.orphan')
    subprocess.Popen([sys.executable, '-c',
                      'import pathlib, sys, time; time.sleep(3); pathlib.Path(sys.argv[1]).write_text("orphan")',
                      str(marker)])
with log.open('a') as handle: handle.write(json.dumps({'verified': True}) + '\\n')
print('merged source and target verified; waiting for bounded check', flush=True)
time.sleep(2)
''')
    command = [sys.executable, str(validator), str(root), str(calls)]
    _policy(root, command, 1)

    first = reconcile_open_review_health(root)
    assert first[0]['outcome'] == 'blocked'
    action = load_action(turn.action_id, root=root)
    assert action['attempt_count'] == 1
    failed = action['attempts'][0]
    assert failed['completion_metadata']['reason'] == 'repository_checks_timed_out'
    assert failed['completion_metadata']['checks'][0]['returncode'] == 124
    assert 'merged source and target verified' in failed['completion_metadata']['checks'][0]['stdout']
    assert _git(root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001').split()[0] == turn.observed_source_sha
    assert not pushes.exists()

    load_feature_tools()
    refused = invoke_feature_tool(
        'feat_035_001', 'publish_review_resolution',
        {'action_id': turn.action_id}, root=root,
    )
    assert refused['reason'] == 'validation_budget_transient_backoff'
    for _ in range(2):
        reconcile_open_review_health(root)
    _monitor_in_new_process(root)
    assert load_action(turn.action_id, root=root)['attempt_count'] == 1
    assert len(calls.read_text().splitlines()) == 1
    budget = read_incident_budget(turn.action_id, root=root)
    assert budget is not None
    assert budget['charged']['tool_attempts'] == 1
    assert len(budget['operations']) == 1
    assert _git(root, 'rev-parse', 'HEAD') == head
    assert not pushes.exists()

    # A changed operator-owned policy is new evidence; no Task/source edit or
    # resetting failed attempts is required. The incident-wide transient
    # backoff remains authoritative across that policy correction.
    _policy(root, command, 10)
    time.sleep(6)
    result = invoke_feature_tool(
        'feat_035_001', 'publish_review_resolution',
        {'action_id': turn.action_id}, root=root,
    )
    assert result['recovery_state'] == 'completed'
    action = load_action(turn.action_id, root=root)
    assert action['recovery_state'] == 'completed'
    assert action['attempt_count'] == 2
    assert action['attempts'][0] == failed
    assert action['attempts'][1]['outcome'] == 'succeeded'
    assert len(action['review_publication_generations']) == 2
    assert result['incident_id'] == turn.action_id
    assert result['claim_id'] == f'review-publication:{turn.action_id}'
    assert result['operation_id']
    assert _git(root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001').split()[0] == head
    assert len(pushes.read_text().splitlines()) == 1
    _monitor_in_new_process(root)
    assert len(calls.read_text().splitlines()) == 2
    budget = read_incident_budget(turn.action_id, root=root)
    assert budget is not None
    assert budget['charged']['tool_attempts'] == 2
    assert len(budget['operations']) == 2
    assert not calls.with_suffix('.orphan').exists(), 'timed-out validator children must be stopped'
    assert load_action(turn.action_id, root=root)['recovery_state'] == 'completed'
    assert len(pushes.read_text().splitlines()) == 1


def test_unavailable_policy_profile_waits_before_claim_then_resumes_same_incident(
    tmp_path, monkeypatch
):
    """Preflight refusal survives sweeps without consuming or publishing."""

    root, turn = _resolved_review(tmp_path, monkeypatch)
    tested_head = _git(root, 'rev-parse', 'HEAD')
    remote_head = _git(
        root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001'
    ).split()[0]
    calls = tmp_path / 'corrected-profile-calls.jsonl'
    unavailable = tmp_path / 'policy-owner-validator-unavailable'
    _policy(
        root,
        [str(unavailable)],
        10,
        owner='release-policy-owner',
        profile='release.review-recovery',
    )

    first = reconcile_open_review_health(root)
    assert first[0]['outcome'] == 'blocked'
    waiting = load_action(turn.action_id, root=root)
    assert waiting['recovery_state'] == 'pending'
    assert waiting['attempt_count'] == 0
    assert read_incident_budget(turn.action_id, root=root) is None
    assert _git(
        root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001'
    ).split()[0] == remote_head

    for _ in range(2):
        reconcile_open_review_health(root)
    restarted = _monitor_in_new_process(root)
    assert 'blocked' in restarted.stdout
    assert load_action(turn.action_id, root=root) == waiting
    assert read_incident_budget(turn.action_id, root=root) is None
    assert not calls.exists()

    validator = tmp_path / 'approved_policy_validator.py'
    validator.write_text(
        "import json, pathlib, sys\n"
        "root, log = map(pathlib.Path, sys.argv[1:])\n"
        "assert (root / 'source.txt').read_text().strip() == 'source'\n"
        "assert (root / 'target.txt').read_text().strip() == 'target'\n"
        "with log.open('a') as handle: handle.write(json.dumps({'head': 'tested'}) + '\\\\n')\n"
    )
    command = [sys.executable, str(validator), str(root), str(calls)]
    _policy(
        root,
        command,
        10,
        owner='release-policy-owner',
        profile='release.review-recovery',
    )
    load_feature_tools()
    result = invoke_feature_tool(
        'feat_035_001', 'publish_review_resolution',
        {'action_id': turn.action_id}, root=root,
    )

    assert result['recovery_state'] == 'completed'
    assert result['incident_id'] == turn.action_id
    assert result['claim_id'] == f'review-publication:{turn.action_id}'
    completed = load_action(turn.action_id, root=root)
    assert completed['attempt_count'] == 1
    generation = completed['attempts'][0]['completion_metadata'][
        'publication_generation'
    ]
    assert generation['source_head'] == tested_head
    assert generation['validation_command'] == command
    assert generation['validation_profile'] == {
        'id': 'release.review-recovery',
        'coverage_class': 'review_publication',
        'policy_owner': 'release-policy-owner',
        'approval_version': '1',
        'attempt_budget': 1,
    }
    budget = read_incident_budget(turn.action_id, root=root)
    assert budget is not None
    operation = budget['operations'][result['operation_id']]
    assert operation['claim_id'] == result['claim_id']
    assert operation['state'] == 'settled'
    assert operation['attributes']['validation_profile']['id'] == generation[
        'validation_profile'
    ]['id']
    assert len(calls.read_text().splitlines()) == 1
    assert _git(
        root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001'
    ).split()[0] == tested_head

    _monitor_in_new_process(root)
    assert len(calls.read_text().splitlines()) == 1
    assert load_action(turn.action_id, root=root) == completed


def test_deterministic_review_retries_require_new_material_within_original_budget(tmp_path, monkeypatch):
    root, turn = _resolved_review(tmp_path, monkeypatch)
    calls = tmp_path / "validator-calls.txt"
    validator = tmp_path / "validator.py"
    validator.write_text(
        "import pathlib, sys\n"
        "assert pathlib.Path('source.txt').read_text().strip() == 'source'\n"
        "with pathlib.Path(sys.argv[1]).open('a') as log: log.write(sys.argv[2] + '\\n')\n"
        "raise SystemExit(int(sys.argv[2]))\n"
    )
    command = [sys.executable, str(validator), str(calls)]
    _policy(root, [*command, "1"], 10)
    load_feature_tools()

    def publish():
        return invoke_feature_tool(
            'feat_035_001', 'publish_review_resolution',
            {'action_id': turn.action_id}, root=root,
        )

    assert publish()['recovery_state'] == 'awaiting_owner_decision'
    original = read_incident_budget(turn.action_id, root=root)
    assert original['charged']['tool_attempts'] == 1
    assert publish()['reason'] == 'validation_budget_deterministic_material_unchanged'
    _monitor_in_new_process(root)
    _git(root, 'commit', '--allow-empty', '-m', 'Cosmetic commit')
    assert publish()['reason'] == 'validation_budget_deterministic_material_unchanged'
    assert calls.read_text().splitlines() == ['1']

    _policy(root, [*command, "2"], 10)
    assert publish()['recovery_state'] == 'awaiting_owner_decision'
    _policy(root, [*command, "1"], 10)
    assert publish()['reason'] == 'validation_budget_deterministic_material_unchanged'
    assert calls.read_text().splitlines() == ['1', '2']
    assert _git(root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001').split()[0] == turn.observed_source_sha

    _policy(root, [*command, "0"], 10)
    assert publish()['recovery_state'] == 'completed'
    budget = read_incident_budget(turn.action_id, root=root)
    assert budget['incident_id'] == original['incident_id']
    assert budget['original_admitted_at'] == original['original_admitted_at']
    assert budget['policy'] == original['policy']
    assert budget['charged']['tool_attempts'] == 3
    assert len(budget['operations']) == 3
    assert load_action(turn.action_id, root=root)['attempt_count'] == 3
    assert calls.read_text().splitlines() == ['1', '2', '0']
    assert _git(root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001').split()[0] == _git(root, 'rev-parse', 'HEAD')


def test_exhausted_legacy_review_is_not_rearmed_by_policy_change(tmp_path, monkeypatch):
    root, turn = _resolved_review(tmp_path, monkeypatch)
    create_or_load_action(turn.action_id, 'review_rebase', root=root, attempt_bound=1,
                         owning_team={'kind': 'feature_team', 'work_id': 'feat_035_001'})

    def timed_out(context):
        raise ActionFailure('owner_decision', 'legacy timeout',
                            metadata={'reason': 'repository_checks_timed_out'})

    resume_action(turn.action_id, root=root, execute=timed_out)
    # The old monitor resolved the next decision before discovering that its
    # attempt budget was exhausted. Reusing an attempt-number ID then strands
    # the rearmed action behind an already-resolved decision.
    decision_id = f'review-resolution:{turn.action_id}:attempt:2'
    record_owner_decision(turn.action_id, decision_id, root=root, owner='feature_team',
                          metadata={'team_id': 'feat_035_001'})
    record_owner_resolution(turn.action_id, decision_id, 'legacy-resolution', root=root)
    exhausted = resume_action(turn.action_id, root=root,
                              execute=lambda context: pytest.fail('budget must be exhausted'))
    assert exhausted['recovery_state'] == 'blocked'
    prior_attempt = exhausted['attempts'][0]
    validator = tmp_path / 'validate_legacy.py'
    validator.write_text("from pathlib import Path\nassert Path('source.txt').read_text().strip() == 'source'\nassert Path('target.txt').read_text().strip() == 'target'\n")
    _policy(root, [sys.executable, str(validator)], 10)
    result = reconcile_open_review_health(root)
    assert result[0]['outcome'] == 'blocked'
    recovered = load_action(turn.action_id, root=root)
    assert recovered['recovery_state'] == 'awaiting_owner_decision'
    assert recovered['attempt_count'] == 1
    assert recovered['attempts'][0] == prior_attempt
    assert recovered['attempt_bound'] == 1
    assert _git(root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001').split()[0] == turn.observed_source_sha


def test_changed_review_policy_cannot_clear_a_human_gate(tmp_path, monkeypatch):
    root, turn = _resolved_review(tmp_path, monkeypatch)
    create_or_load_action(turn.action_id, 'review_rebase', root=root, attempt_bound=3,
                         recovery_state='awaiting_human_gate', failure_classification='human_gate',
                         owning_team={'kind': 'feature_team', 'work_id': 'feat_035_001'})
    _policy(root, [sys.executable, '-c', "raise AssertionError('must not run')"], 10)
    reconcile_open_review_health(root)
    action = load_action(turn.action_id, root=root)
    assert action['recovery_state'] == 'awaiting_human_gate'
    assert action['attempt_count'] == 0
    assert _git(root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001').split()[0] == turn.observed_source_sha


def test_review_policy_does_not_replace_the_task_full_suite(tmp_path):
    _policy(tmp_path, ['python3', '-m', 'pytest', '-q', 'tests/test_review_health.py'], 30)
    assert validation_command(tmp_path) == ('python3', '-m', 'pytest', '-q')
    assert review_validation_command(tmp_path)[-1] == 'tests/test_review_health.py'
    (tmp_path / 'cascade.toml').write_text('')
    assert review_validation_command(tmp_path) == validation_command(tmp_path)
    (tmp_path / 'cascade.toml').write_text('[validation]\nreview_command = "echo success"\n')
    with pytest.raises(ValueError, match='argv array'):
        review_validation_command(tmp_path)


@pytest.mark.parametrize('race', ['source', 'policy'])
def test_checks_cannot_publish_a_different_head_or_policy(tmp_path, monkeypatch, race):
    root, turn = _resolved_review(tmp_path, monkeypatch)
    validator = tmp_path / 'change_during_checks.py'
    if race == 'source':
        validator.write_text('''
from pathlib import Path
import subprocess
Path('new-unvalidated.txt').write_text('arrived while checks were running')
subprocess.run(['git', 'add', 'new-unvalidated.txt'], check=True)
subprocess.run(['git', 'commit', '-m', 'concurrent source change'], check=True)
''')
    else:
        validator.write_text("from pathlib import Path\np = Path('cascade.toml')\np.write_text(p.read_text().replace('review_timeout_seconds = 10', 'review_timeout_seconds = 20'))\n")
    _policy(root, [sys.executable, str(validator)], 10)
    result = reconcile_open_review_health(root)
    assert result[0]['outcome'] == 'blocked'
    action = load_action(turn.action_id, root=root)
    expected = 'source_head_changed' if race == 'source' else 'validation_policy_changed'
    assert action['attempts'][0]['completion_metadata']['reason'] == expected
    assert _git(root, 'ls-remote', 'origin', 'refs/heads/feat/feat_035_001').split()[0] == turn.observed_source_sha
