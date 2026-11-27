from dataclasses import replace
from pathlib import Path
import os
import py_compile
import subprocess
import sys
import time

import pytest

from cascade import review_rebase, review_validation
from cascade.review_owner import current_review_owner, review_owner_exited
from cascade.review_validation import (
    ExactMergeCandidate,
    MergeCandidateRefusal,
    ReviewValidationAdmissionError,
    approved_review_validation_profile,
    inspect_exact_validation_material,
    materialize_exact_merge_candidate,
    preflight_review_validation,
    run_review_validation,
    review_validation_timeout,
    validate_exact_merge_candidate,
)
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
        "python3",
        "-m",
        "pytest",
        "-q",
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


def test_review_validation_profile_binds_owner_approval_and_feasibility(tmp_path):
    (tmp_path / "cascade.toml").write_text(
        """[validation]
review_command = ["missing-validator-binary", "--check"]
review_timeout_seconds = 17
review_profile_id = "repository.review"
review_policy_owner = "release_team"
review_approval_version = "2026-11"
review_coverage_class = "review_and_adjacent"
""",
        encoding="utf-8",
    )
    profile = approved_review_validation_profile(tmp_path)
    assert profile.profile_id == "repository.review"
    assert profile.policy_owner == "release_team"
    assert profile.approval_version == "2026-11"
    assert profile.coverage_class == "review_and_adjacent"
    assert profile.timeout_seconds == 17
    with pytest.raises(ReviewValidationAdmissionError, match="executable"):
        preflight_review_validation(profile, cwd=tmp_path)


def test_exact_material_inspection_precedes_admission_and_binds_complete_identity(
    tmp_path: Path,
) -> None:
    root, source, target = _candidate_repo(tmp_path)
    command = (sys.executable, "-c", "")
    profile = replace(
        approved_review_validation_profile(root, command=command), timeout_seconds=17
    )
    review = {
        "review_id": "42",
        "review_url": "https://forge.invalid/reviews/42",
        "generation": "generation-7",
        "source_ref": "feature/source",
        "target_ref": "main",
    }

    inspected = inspect_exact_validation_material(
        root, source, target, profile=profile, review_identity=review
    )

    assert inspected.material is not None
    identity = inspected.material.identity
    assert identity["candidate"]["source_sha"] == source
    assert identity["candidate"]["target_sha"] == target
    assert identity["candidate"]["result_commit"]
    assert identity["candidate"]["result_tree"]
    assert identity["review"] == review
    assert identity["profile"] == {
        "id": profile.profile_id,
        "argv": list(command),
        "coverage_class": profile.coverage_class,
        "policy_owner": profile.policy_owner,
        "approval_revision": profile.approval_version,
        "timeout_seconds": 17,
        "attempt_budget": 1,
    }
    assert identity["runtime"]["dependency_revision"]
    assert identity["runtime"]["executable_sha256"] != "unavailable"
    assert identity["runtime"]["import_roots"] == ["."]


def test_duplicate_lifecycle_document_blocks_before_checks_and_push(
    tmp_path, monkeypatch
):
    root, turn = _execution_ready_turn(tmp_path)
    execution = review_rebase.execute_review_rebase(
        turn, authorized_paths=("source.txt",)
    )
    original = next(root.glob("docs/features/**/*.md"))
    duplicate = root / "docs/features/3_completed" / original.name
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    duplicate.write_text(original.read_text())
    _git(root, "add", "docs")
    _git(root, "commit", "-m", "simulate duplicate after conflict resolution")
    execution = replace(execution, source_head=_git(root, "rev-parse", "HEAD"))
    monkeypatch.setattr(
        review_validation,
        "run_review_validation",
        lambda *a, **k: pytest.fail("checks must not run"),
    )
    result = review_rebase.check_and_publish_review_rebase(turn, execution)
    assert not result.published
    assert result.blocker.code == "board_validation_failed"
    assert (
        _git(root, "ls-remote", "origin", f"refs/heads/{turn.source_ref}").split()[0]
        == turn.observed_source_sha
    )
    assert duplicate.exists()  # Never guess which document should be removed.


def test_timeout_is_typed_and_never_pushes(tmp_path, monkeypatch):
    root, turn = _execution_ready_turn(tmp_path)
    execution = review_rebase.execute_review_rebase(
        turn, authorized_paths=("source.txt",)
    )
    monkeypatch.setattr(
        review_rebase,
        "validation_command",
        lambda r: (sys.executable, "-c", "import time; time.sleep(30)"),
    )
    monkeypatch.setattr(review_rebase, "review_validation_timeout", lambda r: 0.1)
    result = review_rebase.check_and_publish_review_rebase(turn, execution)
    assert result.blocker.code == "repository_checks_timed_out"
    assert (
        _git(root, "ls-remote", "origin", f"refs/heads/{turn.source_ref}").split()[0]
        == turn.observed_source_sha
    )


def test_timeout_stops_validation_descendants(tmp_path):
    script = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); pathlib.Path('child.pid').write_text(str(p.pid)); time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_review_validation((sys.executable, "-c", script), cwd=tmp_path, timeout=1)
    pid = int((tmp_path / "child.pid").read_text())
    stat = Path(f"/proc/{pid}/stat")
    # SIGKILL delivery and descendant teardown can lag the reaped group leader.
    # Still fail if a child survives the bounded scheduler allowance.
    deadline = time.monotonic() + 1
    while True:
        try:
            state = stat.read_text().split(") ")[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            # Linux procfs can return ESRCH if the descendant exits between
            # opening stat and reading it. Both errors prove it is gone.
            break
        if state == "Z":
            break
        assert time.monotonic() < deadline, f"validation descendant still {state}"
        time.sleep(0.01)


def test_validation_output_is_bounded(tmp_path):
    result = run_review_validation(
        (sys.executable, "-c", "print('x'*100000)"), cwd=tmp_path, timeout=5
    )
    assert result.returncode == 0 and len(result.stdout) == 65536


@pytest.mark.parametrize("value", ["true", "0", "3601", '"unbounded"'])
def test_invalid_timeout_config_rejected(tmp_path, value):
    (tmp_path / "cascade.toml").write_text(
        "[validation]\nreview_timeout_seconds = " + value + "\n"
    )
    with pytest.raises(ValueError):
        review_validation_timeout(tmp_path)


def test_killed_publication_owner_is_returned_to_team_exactly_once(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    actions.create_or_load_action(
        "publication:test",
        "review_rebase",
        root=root,
        attempt_bound=3,
        owning_team={"kind": "epic_team", "work_id": "epic_001"},
    )
    code = """import cascade.board
from pathlib import Path
import os,sys
from cascade.task.action_recovery import resume_action
resume_action('publication:test', root=Path(sys.argv[1]), execute=lambda ctx: os._exit(9))
"""
    child = subprocess.run([sys.executable, "-c", code, str(root)])
    assert child.returncode == 9
    before = actions.load_action("publication:test", root=root)
    assert before["recovery_state"] == "running"
    assert before["execution_claim"]["owner_process"]["pid"] > 0
    assert actions.reconcile_abandoned_review_publications(root=root) == 1
    assert actions.reconcile_abandoned_review_publications(root=root) == 0
    after = actions.load_action("publication:test", root=root)
    assert after["recovery_state"] == "awaiting_owner_decision"
    assert "execution_claim" not in after
    assert (
        after["attempts"][-1]["completion_metadata"]["reason"]
        == "publication_owner_exited"
    )
    events, _ = read_events("epic_001", 0, root=root)
    assert len(events) == 1 and events[0].type == "BranchActionRecoveryRequested"
    assert "epic_001" in actions.pending_recovery_team_ids(root=root)


def test_live_claim_is_not_reclaimed_due_to_age_and_legacy_is_not_guessed(tmp_path):
    root = make_repo(tmp_path, git=False)
    actions.create_or_load_action(
        "publication:live", "review_rebase", root=root, attempt_bound=3
    )
    actions._claim_resume_attempt("publication:live", root=root)
    assert actions.reconcile_abandoned_review_publications(root=root) == 0
    assert (
        actions.load_action("publication:live", root=root)["recovery_state"]
        == "running"
    )
    assert not review_owner_exited(None)
    assert not review_owner_exited({"pid": os.getpid()})
    assert not review_owner_exited(current_review_owner())
    reused = {**current_review_owner(), "start_ticks": "different"}
    assert review_owner_exited(reused)


def test_unknown_process_evidence_never_reclaims(monkeypatch):
    import cascade.review_owner as module

    owner = current_review_owner()

    def denied(pid):
        raise PermissionError("unreadable process")

    monkeypatch.setattr(module, "process_identity", denied)
    assert not module.review_owner_exited(owner)


def test_validation_scans_physical_checkout_in_split_session(tmp_path):
    from cascade.board.context import set_project_context
    from cascade.workspace.types import ProjectContext
    from cascade.review_validation import validate_publication_board
    from cascade.board.errors import SchemaError

    product = make_repo(tmp_path / "product", git=False)
    tracking = make_repo(tmp_path / "tracking", git=False)
    add_doc(product, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        product,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    original = next(product.glob("docs/features/1_backlog/*.md"))
    duplicate = product / "docs/features/3_completed" / original.name
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

    path = tmp_path / "docs/features/1_backlog/feat_001_broken.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nid: feat_001\n---\nIncomplete work document")
    with pytest.raises(SchemaError):
        validate_publication_board(tmp_path)


def test_changed_validation_material_uses_remaining_original_budget(tmp_path, monkeypatch):
    from cascade.epic.dependency_approvals import AuthenticatedHuman
    from cascade.feature.review_recovery import publish_review_resolution
    from cascade.task.incident_budget import DEFAULT_LIMITS, extend_incident_budget, read_incident_budget

    root, turn = _execution_ready_turn(tmp_path)
    (root / ".git/info/exclude").write_text(".cascade/\ndocs/_queue/\ncascade.toml\n")
    _git(root, "merge", "epic/epic_035", "--no-edit")
    monkeypatch.setattr(
        review_rebase,
        "validation_command",
        lambda r: (sys.executable, "-c", "raise SystemExit(1)"),
    )
    for _ in range(2):
        result = publish_review_resolution(
            turn.action_id, feature_id="feat_035_001", root=root
        )
        assert result["recovery_state"] == "awaiting_owner_decision"
        assert actions.load_action(turn.action_id, root=root)["attempt_count"] == 1
    budget = read_incident_budget(turn.action_id, root=root)
    spent = budget["charged"]["process_seconds"]
    assert spent > 0
    # Changed material is eligible, but a worst-case reservation that exceeds
    # the original remaining process allowance still requires independent authority.
    (root / "cascade.toml").write_text(
        f"[validation]\nreview_timeout_seconds = {DEFAULT_LIMITS['process_seconds']}\n"
    )
    monkeypatch.setattr(
        review_rebase, "validation_command", lambda r: (sys.executable, "-c", "")
    )
    refused = publish_review_resolution(
        turn.action_id, feature_id="feat_035_001", root=root
    )
    assert refused["recovery_state"] == "awaiting_owner_decision"
    assert refused["reason"] == "validation_budget_cumulative_allowance_exhausted"
    assert actions.load_action(turn.action_id, root=root)["attempt_count"] == 1
    extend_incident_budget(
        turn.action_id,
        AuthenticatedHuman("human:review-operator"),
        "approved corrected validation policy",
        {"source": "review-policy-approval"},
        {"process_seconds": spent},
        root=root,
    )
    result = publish_review_resolution(
        turn.action_id, feature_id="feat_035_001", root=root
    )
    assert result["recovery_state"] == "completed"
    assert actions.load_action(turn.action_id, root=root)["attempt_count"] == 2


def test_dead_claim_check_precedes_failing_board_projection(tmp_path, monkeypatch):
    import cascade.automation
    import cascade.watchdog.loop as loop

    calls = []
    monkeypatch.setattr(
        actions,
        "reconcile_abandoned_review_publications",
        lambda **k: calls.append("reconcile"),
    )
    monkeypatch.setattr(cascade.automation, "maybe_sync_briefs", lambda r: None)

    def invalid(root):
        calls.append("board")
        raise ValueError("duplicate document")

    monkeypatch.setattr(loop, "_tick_scan_active", invalid)
    with pytest.raises(ValueError):
        loop.watchdog_tick(root=tmp_path)
    assert calls == ["reconcile", "board"]


def _candidate_repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "candidate-repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    (root / "product.py").write_text("VALUE = 'bad1'\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_source.py").write_text(
        "from product import VALUE\n\ndef test_source():\n    assert len(VALUE) == 4\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")

    _git(root, "checkout", "-b", "target")
    (tests / "test_boot.py").write_text(
        "from product import VALUE\n\ndef test_task_boot_contract():\n    assert VALUE == 'good'\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "incompatible target boot assertion")
    target = _git(root, "rev-parse", "HEAD")

    _git(root, "checkout", "-b", "source", base)
    return root, _git(root, "rev-parse", "HEAD"), target


def test_exact_candidate_real_git_red_then_equal_size_same_second_green(tmp_path):
    root, source, target = _candidate_repo(tmp_path)
    command = (sys.executable, "-m", "pytest", "-q", "tests/test_boot.py")
    source_only = subprocess.run(
        (sys.executable, "-m", "pytest", "-q", "tests/test_source.py"),
        cwd=root, capture_output=True, text=True,
    )
    assert source_only.returncode == 0

    original_stat = (root / "product.py").stat()
    py_compile.compile(str(root / "product.py"), doraise=True)
    bytecode = next((root / "__pycache__").glob("product.*.pyc"))
    _git(root, "add", "-f", str(bytecode.relative_to(root)))
    _git(root, "commit", "-m", "retain source bytecode fixture")
    source = _git(root, "rev-parse", "HEAD")
    red = validate_exact_merge_candidate(
        root, source, target, command=command, timeout=20
    )
    assert red.outcome == "product_assertion"
    assert red.returncode == 1
    assert "test_task_boot_contract" in red.stdout
    assert "keep the approved assertion" in red.owner_action
    assert red.candidate is not None and not red.candidate.checkout.exists()
    assert bytecode.exists()  # Candidate cleanup never deletes the shared cache.

    before = (root / "product.py").read_bytes()
    (root / "product.py").write_text("VALUE = 'good'\n", encoding="utf-8")
    assert len((root / "product.py").read_bytes()) == len(before)
    os.utime(
        root / "product.py",
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    _git(root, "add", "product.py")
    _git(root, "commit", "-m", "satisfy target boot assertion")
    corrected = _git(root, "rev-parse", "HEAD")
    green = validate_exact_merge_candidate(
        root, corrected, target, command=command, timeout=20
    )
    assert green.outcome == "passed", (green.stdout, green.stderr)
    assert green.candidate is not None
    assert green.candidate.source_sha == corrected
    assert green.candidate.target_sha == target
    assert green.candidate.result_commit and green.candidate.result_tree
    assert green.dependency_revision == green.environment_revision["dependency_revision"]
    assert not green.candidate.checkout.exists()
    assert bytecode.exists()


def test_exact_candidate_materialization_is_private_deterministic_and_typed(tmp_path):
    root, source, target = _candidate_repo(tmp_path)
    head_before = _git(root, "rev-parse", "HEAD")
    status_before = _git(root, "status", "--porcelain=v1")
    refs_before = _git(root, "show-ref")
    index_before = (root / ".git/index").read_bytes()
    identities = []
    checkouts = []
    for _ in range(2):
        with materialize_exact_merge_candidate(root, source, target) as result:
            assert isinstance(result, ExactMergeCandidate)
            assert result.checkout.is_dir()
            identities.append((result.result_commit, result.result_tree))
            checkouts.append(result.checkout)
    assert identities[0] == identities[1]
    assert all(not checkout.exists() for checkout in checkouts)
    assert _git(root, "rev-parse", "HEAD") == head_before
    assert _git(root, "status", "--porcelain=v1") == status_before
    assert _git(root, "show-ref") == refs_before
    assert (root / ".git/index").read_bytes() == index_before

    with materialize_exact_merge_candidate(root, None, target) as missing:
        assert isinstance(missing, MergeCandidateRefusal)
        assert missing.kind == "missing"
    with materialize_exact_merge_candidate(root, "0" * 40, target) as unknown:
        assert isinstance(unknown, MergeCandidateRefusal)
        assert unknown.kind == "unknown"


def test_exact_candidate_conflict_and_malformed_board_refuse_before_spawn(tmp_path):
    root, source, target = _candidate_repo(tmp_path)
    _git(root, "checkout", "source")
    (root / "shared.txt").write_text("source\n", encoding="utf-8")
    _git(root, "add", "shared.txt")
    _git(root, "commit", "-m", "source shared")
    conflict_source = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "target")
    (root / "shared.txt").write_text("target\n", encoding="utf-8")
    _git(root, "add", "shared.txt")
    _git(root, "commit", "-m", "target shared")
    conflict_target = _git(root, "rev-parse", "HEAD")
    with materialize_exact_merge_candidate(
        root, conflict_source, conflict_target
    ) as conflict:
        assert isinstance(conflict, MergeCandidateRefusal)
        assert conflict.kind == "conflict"
        assert conflict.conflicted_paths == ("shared.txt",)

    _git(root, "checkout", "source")
    broken = root / "docs/tasks/2_active/task_broken.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("---\nid: task_broken\n---\ninvalid", encoding="utf-8")
    _git(root, "add", "docs")
    _git(root, "commit", "-m", "malformed lifecycle document")
    malformed_source = _git(root, "rev-parse", "HEAD")
    marker = tmp_path / "validator-spawned"
    result = validate_exact_merge_candidate(
        root, malformed_source, target,
        command=(sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"),
        timeout=10,
    )
    assert result.outcome == "fixture_environment"
    assert "lifecycle documents" in result.owner_action
    assert not marker.exists()
