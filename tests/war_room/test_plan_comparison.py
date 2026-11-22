"""Draft planning evidence must be visible before formal publication."""
from pathlib import Path
import subprocess

from cascade.board.store import read_doc, write_doc
from cascade.war_room.plan_comparison import plan_comparison, compare_document
from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
from tests.support import make_repo, add_doc


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def commit(root, message):
    git(root, 'add', '.')
    git(root, 'commit', '-qm', message)
    return git(root, 'rev-parse', 'HEAD')


def test_draft_keeps_full_context_and_all_designs_across_multiple_commits(tmp_path):
    root = make_repo(tmp_path)
    add_doc(root, id='epic_001', title='Recovery', tier='epic')
    (root / 'DESIGN.md').write_text('# Existing design\n\nUnchanged context.\n')
    (root / 'old').mkdir()
    (root / 'old/DESIGN.md').write_text('Retired component\n')
    base = commit(root, 'baseline')
    # A registered owner is sufficient; no architecture publication is created.
    save_registry(root, [IntegrationWorktree('epic', 'epic_001', git(root, 'branch', '--show-current'), root, base)])
    doc = read_doc('epic_001', root=root)
    doc.body += '\n## Recovery policy\n\nPreserve history.\n'
    write_doc(doc, root=root)
    (root / 'DESIGN.md').write_text('# Existing design\n\nUnchanged context.\n\nNew requirement.\n')
    commit(root, 'first planning changes')
    (root / 'new').mkdir()
    (root / 'new/DESIGN.md').write_text('# New component\n')
    (root / 'old/DESIGN.md').unlink()
    proposed = commit(root, 'second planning changes')
    # Working tree edits cannot silently enter a revision-pinned comparison.
    (root / 'DESIGN.md').write_text('Uncommitted draft\n')
    result = plan_comparison(root, 'epic_001')
    assert result['state'] == 'draft'
    assert result['current_revision'] == base
    assert result['proposed_revision'] == proposed
    assert 'Preserve history.' in result['plan']['proposed']
    assert 'Preserve history.' not in result['plan']['current']
    designs = {d['path']: d for d in result['designs']}
    assert set(designs) == {'DESIGN.md', 'new/DESIGN.md', 'old/DESIGN.md'}
    assert 'Unchanged context.' in designs['DESIGN.md']['current']
    assert 'New requirement.' in designs['DESIGN.md']['proposed']
    assert 'Uncommitted' not in designs['DESIGN.md']['proposed']
    assert designs['new/DESIGN.md']['current'] == ''
    assert designs['old/DESIGN.md']['proposed'] == ''
    assert designs['DESIGN.md']['added_lines'] == [4, 5]


def test_undispatched_feature_uses_owning_epic_branch(tmp_path):
    root = make_repo(tmp_path)
    add_doc(root, id='epic_001', title='Recovery', tier='epic')
    base = commit(root, 'baseline')
    save_registry(root, [IntegrationWorktree('epic', 'epic_001', git(root, 'branch', '--show-current'), root, base)])
    add_doc(root, id='feat_001_001', title='Repair', tier='feature', parent='epic_001')
    commit(root, 'feature brief')
    result = plan_comparison(root, 'feat_001_001')
    assert result['state'] == 'draft'
    assert result['owner_work_id'] == 'epic_001'
    assert result['plan']['current'] == ''
    assert result['plan']['added_lines']


def test_missing_branch_is_unavailable_not_no_changes(tmp_path):
    root = make_repo(tmp_path)
    add_doc(root, id='epic_001', title='Recovery', tier='epic')
    result = plan_comparison(root, 'epic_001')
    assert result['state'] == 'unavailable'
    assert 'registered planning branch' in result['message']


def test_changed_line_ranges_preserve_unchanged_document_context():
    result = compare_document('DESIGN.md', 'heading\nold\ncontext\n', 'heading\nnew\ncontext\n')
    assert result['removed_lines'] == [2]
    assert result['added_lines'] == [2]
    assert result['current'].endswith('context\n')


def test_draft_diagram_polling_keeps_snapshot_pair_when_planning_advances(tmp_path):
    from cascade.war_room.plan_comparison import draft_diagrams
    from cascade.workspace.architecture_snapshots import ArchitectureSnapshotStore
    from cascade.workspace.types import ProjectContext

    root = make_repo(tmp_path)
    add_doc(root, id='epic_001', title='Recovery', tier='epic')
    base = commit(root, 'baseline')
    checkout = root / '.cascade/worktrees/epic_epic_001'
    checkout.parent.mkdir(parents=True, exist_ok=True)
    git(root, 'worktree', 'add', '-b', 'epic/epic_001', str(checkout))
    save_registry(root, [IntegrationWorktree('epic', 'epic_001', 'epic/epic_001', checkout, base)])
    (checkout / 'proposal.txt').write_text('first proposal\n')
    first_head = commit(checkout, 'first proposal')
    first = draft_diagrams(root, 'epic_001')
    assert first['state'] == 'missing_mapping'  # An unavailable model is explicit.
    (checkout / 'proposal.txt').write_text('later proposal\n')
    commit(checkout, 'later proposal')
    polled = draft_diagrams(root, 'epic_001', snapshot_ids=first['snapshot_ids'])
    assert polled['snapshot_ids'] == first['snapshot_ids']
    assert polled['approval_context'] is None
    with ArchitectureSnapshotStore(ProjectContext.colocated(root), root) as store:
        assert store.get(polled['snapshot_ids']['proposed']).descriptor['revisions']['code'] == first_head


def test_project_projection_preserves_current_main_and_applies_proposal_without_checkout_changes(tmp_path):
    from cascade.war_room.plan_comparison import project_projection_revision

    root = make_repo(tmp_path)
    (root / 'architecture.txt').write_text('existing project\n')
    base = commit(root, 'project baseline')
    git(root, 'branch', 'proposal', base)
    (root / 'landed.txt').write_text('already delivered on main\n')
    current = commit(root, 'unrelated work lands')
    branch = root.parent / 'proposal'
    git(root, 'worktree', 'add', str(branch), 'proposal')
    (branch / 'architecture.txt').write_text('expected project after completion\n')
    proposal = commit(branch, 'proposed architecture')
    (root / 'architecture.txt').write_text('local uncommitted work must survive\n')
    status = git(root, 'status', '--porcelain')
    index_tree = git(root, 'write-tree')
    result = project_projection_revision(root, current, proposal)
    assert result not in {current, proposal}
    assert git(root, 'show', result + ':landed.txt') == 'already delivered on main'
    assert git(root, 'show', result + ':architecture.txt') == 'expected project after completion'
    assert git(root, 'rev-parse', 'HEAD') == current
    assert git(branch, 'rev-parse', 'HEAD') == proposal
    assert git(root, 'write-tree') == index_tree
    assert git(root, 'status', '--porcelain') == status
    assert (root / 'architecture.txt').read_text() == 'local uncommitted work must survive\n'
    assert project_projection_revision(root, current, proposal) == result


def test_project_projection_reports_conflicts_instead_of_removing_current_work(tmp_path):
    import pytest
    from cascade.war_room.plan_comparison import project_projection_revision

    root = make_repo(tmp_path)
    (root / 'architecture.txt').write_text('original\n')
    base = commit(root, 'baseline')
    git(root, 'branch', 'proposal', base)
    (root / 'architecture.txt').write_text('already delivered change\n')
    current = commit(root, 'main change')
    branch = root.parent / 'proposal'
    git(root, 'worktree', 'add', str(branch), 'proposal')
    (branch / 'architecture.txt').write_text('conflicting proposal\n')
    proposal = commit(branch, 'proposal change')
    with pytest.raises(ValueError, match='conflicts with the current project.*architecture.txt'):
        project_projection_revision(root, current, proposal)
    assert (root / 'architecture.txt').read_text() == 'already delivered change\n'
    assert git(root, 'rev-parse', 'HEAD') == current
    assert git(root, 'status', '--porcelain') == ''


def test_diagram_current_is_latest_project_not_work_item_starting_revision(tmp_path):
    from cascade.war_room.plan_comparison import draft_diagrams
    from cascade.workspace.architecture_snapshots import ArchitectureSnapshotStore
    from cascade.workspace.types import ProjectContext

    root = make_repo(tmp_path)
    add_doc(root, id='epic_001', title='Recovery', tier='epic')
    base = commit(root, 'baseline')
    checkout = root / '.cascade/worktrees/epic_epic_001'
    checkout.parent.mkdir(parents=True, exist_ok=True)
    git(root, 'worktree', 'add', '-b', 'epic/epic_001', str(checkout))
    save_registry(root, [IntegrationWorktree('epic', 'epic_001', 'epic/epic_001', checkout, base)])
    (checkout / 'planned.txt').write_text('proposed change\n')
    proposal = commit(checkout, 'proposal')
    (root / 'already-delivered.txt').write_text('current project\n')
    current = commit(root, 'project advances after epic starts')
    result = draft_diagrams(root, 'epic_001')
    assert result['project_revisions']['current'] == current != base
    assert result['project_revisions']['proposal_source'] == proposal
    with ArchitectureSnapshotStore(ProjectContext.colocated(root), root) as store:
        baseline = store.get(result['snapshot_ids']['current'])
        projected = store.get(result['snapshot_ids']['proposed'])
        assert baseline.descriptor['revisions']['code'] == current
        revision = projected.descriptor['revisions']['code']
        assert git(root, 'show', revision + ':already-delivered.txt') == 'current project'
        assert git(root, 'show', revision + ':planned.txt') == 'proposed change'
    (root / 'next.txt').write_text('next integration\n')
    commit(root, 'project advances during rendering')
    pinned = draft_diagrams(root, 'epic_001', snapshot_ids=result['snapshot_ids'])
    assert pinned['newer_revision_available'] is True
    assert pinned['project_revisions'] == result['project_revisions']


def test_project_target_colors_cover_both_sides_renames_and_moves():
    from types import SimpleNamespace
    from cascade.war_room.plan_comparison import project_target_changes
    from cascade.workspace.c4_diff import C4IdentityChange, C4ContainmentChange

    diff = SimpleNamespace(
        identities=(
            C4IdentityChange('element', 'added', 'added'),
            C4IdentityChange('element', 'removed', 'removed'),
            C4IdentityChange('element', 'modified', 'changed'),
            C4IdentityChange('relationship', 'edge', 'changed'),
            C4IdentityChange('element', 'new-id', 'changed', previous_semantic_id='old-id'),
            C4IdentityChange('element', 'moved', 'unchanged'),
            C4IdentityChange('element', 'stable', 'unchanged'),
        ),
        containment=(C4ContainmentChange('moved', 'old-parent', 'new-parent'),),
    )
    colors = project_target_changes(diff)
    assert colors['added'] == 'added'  # proposed-only green
    assert colors['removed'] == 'removed'  # current-only red
    assert colors['modified'] == colors['edge'] == 'changed'  # amber on both sides
    assert colors['old-id'] == colors['new-id'] == 'changed'
    assert colors['moved'] == 'changed'
    assert colors['stable'] == 'unchanged'


def test_comparison_metadata_exposes_pinned_semantic_details(tmp_path):
    import hashlib
    import json
    from types import SimpleNamespace
    from cascade.war_room.plan_comparison import comparison_metadata
    workspace = {'model': {'softwareSystems': [{
        'id': '1', 'name': 'Project', 'properties': {'cascade.semanticId': 'element.project'},
        'containers': [{'id': '2', 'name': 'Service', 'description': 'Runs jobs',
                        'technology': 'Python', 'tags': 'Worker',
                        'properties': {'cascade.semanticId': 'element.service', 'decision': 'local'}}],
    }]}}
    path = tmp_path / 'workspace.json'
    raw = json.dumps(workspace).encode()
    path.write_bytes(raw)
    artifact = SimpleNamespace(render=SimpleNamespace(
        semantic_workspace=path, semantic_workspace_sha256=hashlib.sha256(raw).hexdigest()))
    metadata = comparison_metadata(artifact)['element.service']
    assert metadata['type'] == 'Container'
    assert metadata['parent'] == 'element.project'
    assert metadata['description'] == 'Runs jobs'
    assert metadata['technology'] == 'Python'
    assert metadata['properties']['decision'] == 'local'
