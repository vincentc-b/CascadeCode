"""Planning-boundary acceptance for declaration, authority, isolation and restart."""

from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
from pathlib import Path
import subprocess

import pytest

from cascade.agent.mcp_wrappers import dispatch_planning_tool, ToolEffectCollector
from cascade.epic.dependency_manifests import (
    StaleDependencyManifestRevision,
    manifest_path,
    read_dependency_manifest_history,
)
from tests.epic.test_dependency_manifest_authoring import (
    board as authoring_board,
    manifest,
    environment,
)
from tests.epic.test_dependency_operation_authority import dependency


@pytest.fixture
def board(tmp_path):
    return authoring_board.__wrapped__(tmp_path)


def dispatch(root, name, args=None, role="epic_manager"):
    return dispatch_planning_tool(
        "epic",
        name,
        args or {},
        scope_id="epic_001",
        repo_root=root,
        collector=ToolEffectCollector(),
        role=role,
    )


@pytest.mark.parametrize("role", ["epic_manager", "epic_architect"])
def test_both_roles_can_read_append_and_reload_real_declaration(board, role):
    payload = manifest(dependency(environment("owned")))
    assert (
        dispatch(board, "read_dependency_manifest", role=role)["manifest_revision"] == 0
    )
    first = dispatch(
        board,
        "write_dependency_manifest",
        {"manifest": payload, "expected_revision": 0},
        role,
    )
    assert first["manifest_revision"] == 1
    assert first["software_dependency_status"]["status"] == "unchecked"
    assert (
        first["software_dependency_status"]["dependencies"][0]["installation_approval"][
            "state"
        ]
        == "missing"
    )
    assert (
        dispatch(
            board,
            "write_dependency_manifest",
            {"manifest": payload, "expected_revision": 1},
            role,
        )["manifest_revision"]
        == 1
    )
    # A fresh interpreter reads the same canonical declaration, no repeated write.
    code = "from pathlib import Path; from cascade.epic.dependency_manifest_authoring import read_dependency_manifest; import json,sys; print(json.dumps(read_dependency_manifest(epic_id='epic_001',root=Path(sys.argv[1]))))"
    import sys

    loaded = subprocess.run(
        [sys.executable, "-c", code, str(board)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(loaded.stdout)["manifest"] == first["manifest"]
    assert len(read_dependency_manifest_history("epic_001", root=board)) == 1


def test_concurrent_planning_authors_get_one_revision_not_last_writer_wins(board):
    payloads = [
        manifest(dependency(environment("a"))),
        manifest(dependency(environment("b"))),
    ]

    def author(payload):
        try:
            return dispatch(
                board,
                "write_dependency_manifest",
                {"manifest": payload, "expected_revision": 0},
            )
        except StaleDependencyManifestRevision:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(author, payloads))
    assert sum(result is not None for result in results) == 1
    assert len(read_dependency_manifest_history("epic_001", root=board)) == 1


def _contend_for_dependency_lock(root, ready, acquired):
    from cascade.epic.dependency_lock import dependency_state_lock

    ready.set()
    with dependency_state_lock(root=Path(root)):
        acquired.set()


def test_owned_worktree_and_human_trunk_share_cross_process_authority_lock(board):
    from cascade.epic.dependency_lock import dependency_state_lock
    from cascade.workspace.integration_worktree import get_integration_worktree

    owning = get_integration_worktree(board, "epic", "epic_001").path
    ctx = multiprocessing.get_context("spawn")
    ready, acquired = ctx.Event(), ctx.Event()
    worker = ctx.Process(
        target=_contend_for_dependency_lock, args=(str(owning), ready, acquired)
    )
    try:
        with dependency_state_lock(root=board):
            worker.start()
            assert ready.wait(10)
            assert not acquired.wait(0.2), (
                "owned author and trunk approver used different flock files"
            )
        assert acquired.wait(10)
        worker.join(10)
        assert worker.exitcode == 0
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join()


def test_split_target_tracking_authoring_stays_in_owned_tracking_worktree(tmp_path):
    from tests.support import add_doc, make_repo
    from cascade.board.context import set_project_context
    from cascade.workspace.types import ProjectContext
    from cascade.workspace.integration_worktree import create_integration_worktree

    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    add_doc(tracking, id="epic_001", title="Active", tier="epic", status="active")
    owned = create_integration_worktree(
        "epic", "epic_001", branch="epic/epic_001", base_ref="HEAD", trunk=tracking
    )
    set_project_context(ProjectContext.split(target, tracking))
    result = dispatch(
        target,
        "write_dependency_manifest",
        {"manifest": manifest(), "expected_revision": 0},
    )
    assert result["manifest_revision"] == 1
    assert manifest_path("epic_001", root=target).is_relative_to(owned.path)
    assert manifest_path("epic_001", root=target).is_file()
    assert not list(target.rglob("_dependency_manifests/*.json"))
    assert (
        dispatch(tracking, "read_dependency_manifest")["manifest"] == result["manifest"]
    )


def test_completed_owner_and_path_escape_cannot_author(board, tmp_path):
    from cascade.board import move_doc
    from cascade.workspace.integration_worktree import get_integration_worktree

    owned = get_integration_worktree(board, "epic", "epic_001").path
    sidecar = owned / "docs/epics/2_active/_dependency_manifests"
    sidecar.symlink_to(tmp_path)
    with pytest.raises(PermissionError, match="path escape"):
        dispatch(
            board,
            "write_dependency_manifest",
            {"manifest": manifest(), "expected_revision": 0},
        )
    sidecar.unlink()
    move_doc("epic_001", "completed", root=owned)
    with pytest.raises(PermissionError, match="active owned Epic"):
        dispatch(
            board,
            "write_dependency_manifest",
            {"manifest": manifest(), "expected_revision": 0},
        )


def test_real_declared_dependency_requires_human_approval_and_trusted_execution(
    board, monkeypatch
):
    from cascade.epic.dependency_approvals import (
        AuthenticatedHuman,
        InstallationApprovalDenied,
        approve_dependency_installations,
    )
    from cascade.epic.dependency_bootstrap import (
        BootstrapEntryScope,
        BootstrapLimits,
        BootstrapScope,
        create_bootstrap,
    )
    from cascade.epic.dependency_evidence import (
        CheckOperationKind,
        CheckResult,
        admit_dependency_check,
        dispatch_dependency_mutation,
        record_trusted_dependency_check_completion,
        compute_dependency_readiness,
    )

    target = environment("owned")
    item = dependency(target)
    dispatch(
        board,
        "write_dependency_manifest",
        {"manifest": manifest(item), "expected_revision": 0},
        "epic_architect",
    )
    bootstrap = create_bootstrap(
        "epic_001",
        BootstrapScope(
            manifest_revision=1,
            entries=(
                BootstrapEntryScope(
                    dependency_id=item.dependency_id,
                    source=item.source,
                    integrity_reference=item.integrity_reference,
                    setup_operation=item.operation,
                    check_operation=item.verification_recipe,
                    paths=(item.install_destination,),
                    destination=item.install_destination,
                    cleanup=item.cleanup_plan,
                ),
            ),
            feasibility_artifacts=(),
            limits=BootstrapLimits(60, 2, 4096),
        ),
        root=board,
    )
    kwargs = dict(
        root=board,
        operation_kind=CheckOperationKind.INSTALL,
        exact_operation=item.operation,
        bootstrap_revision=bootstrap.revision,
    )
    with pytest.raises(InstallationApprovalDenied):
        admit_dependency_check("epic_001", item.dependency_id, **kwargs)
    approval = approve_dependency_installations(
        "epic_001",
        (item.dependency_id,),
        approver=AuthenticatedHuman("operator@example.test"),
        root=board,
    )[0]
    admission = admit_dependency_check(
        "epic_001",
        item.dependency_id,
        approval_reference=approval.approval_id,
        **kwargs,
    )
    executed = []
    assert (
        dispatch_dependency_mutation(
            "epic_001",
            admission.attempt_id,
            lambda: executed.append(item.operation) or "installed",
            root=board,
        )
        == "installed"
    )
    assert executed == [item.operation]
    # Declaration and even admitted execution are not readiness evidence.
    assert not compute_dependency_readiness("epic_001", root=board).ready
    completion = record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=board,
        actual_environment=target,
        result=CheckResult.SUCCEEDED,
        redacted_output="tool 1.2.3",
        selected_version=item.version,
        integrity_reference=item.digest,
    )
    assert completion.authority_current
    assert compute_dependency_readiness("epic_001", root=board).ready
    assert (
        dispatch(board, "read_dependency_manifest")["software_dependency_status"][
            "dependencies"
        ][0]["status"]
        == "ready"
    )

    # The same declared/verified run reaches ordinary signoffs and human approval.
    from cascade.board.store import read_doc, write_doc
    from cascade.workspace.doc_root import resolve_doc_worktree
    from cascade.epic.mint import mint_feature
    from cascade.epic.planning_signoffs import canonical_plan_revision
    from cascade.approvals import approve_epic_plan
    from cascade.watchdog.dispatch import dispatch_feature
    from tests.support import FEATURE_BODY
    from tests.test_approval_selection_gate import _inventory

    inventory = _inventory("offered")
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    owner = resolve_doc_worktree("epic_001", root=board)
    epic = read_doc("epic_001", root=owner)
    epic.meta.provider = "codex"
    epic.meta.models = {
        role: "offered"
        for role in (
            "epic_manager",
            "epic_architect",
            "feature_lead",
            "feature_architect",
            "swe",
        )
    }
    write_doc(epic, root=owner)
    child = mint_feature(
        "Verified dependency implementation",
        body_stub=FEATURE_BODY,
        epic_id="epic_001",
        root=board,
    )
    revision = canonical_plan_revision("epic_001", root=board)
    for role in ("epic_manager", "epic_architect"):
        dispatch(board, "sign_off_plan", {"plan_revision": revision}, role)
    approve_epic_plan("epic_001", root=board, inventory=inventory)
    result = dispatch_feature(child, "human", root=board)
    assert result.ok, result


def test_missing_manifest_projection_and_planning_prompt_explain_authoring(board):
    from cascade.agent.planning_turn import _with_dependency_projection
    from cascade.epic.dependency_status import project_dependency_status
    from cascade.workspace.doc_root import read_doc_resolved

    projection = project_dependency_status("epic_001", root=board)
    assert projection["errors"][0]["code"] == "missing_manifest"
    assert projection["bootstrap"] is None
    assert "Epic Manager or Architect" in projection["errors"][0]["detail"]
    prompt = _with_dependency_projection(
        "Plan the Epic",
        owner_path=read_doc_resolved("epic_001", root=board).meta.path,
        root=board,
    )
    assert (
        "read_dependency_manifest" in prompt and "write_dependency_manifest" in prompt
    )
    assert "expected_revision" in prompt
    dispatch(
        board,
        "write_dependency_manifest",
        {"manifest": manifest(), "expected_revision": 0},
    )
    projection = project_dependency_status("epic_001", root=board)
    assert not any(row["code"] == "missing_manifest" for row in projection["errors"])
    assert projection["explicit_no_dependencies"] is True
