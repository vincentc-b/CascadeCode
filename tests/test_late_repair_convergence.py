"""Cross-boundary acceptance for late Feature repair convergence.

These scenarios intentionally use real Git worktrees, Task delivery, Feature
repair receipts, review generations, and parent integration. Provider discovery/compatibility and
scripted model/forge transport are deterministic; no lifecycle or review result
is manufactured.
"""

from __future__ import annotations

import subprocess
import hashlib
import hmac
import json
import os
import shutil
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest

import cascade.review as review
from cascade.agent.discovery.types import ProviderCompatibilityEvidence
from cascade.board.errors import GitError
from cascade.board.context import set_project_context
from cascade.board.store import move_doc, read_doc, write_doc
from cascade.boss.merge import merge_task_branch
from cascade.boss.rollup import write_closeout
from cascade.comments.store import comment
from cascade.feature.mint import mint_task
from cascade.feature.repair import (
    FeatureRepairError,
    admit_feature_repair,
    current_feature_repair_record,
    inspect_feature_repair,
)
from cascade.agent.types import RoleResult
from cascade.task.action_recovery import recovery_actions
from cascade.task.execution import mark_running
from cascade.task.git_tools import swe_commit, swe_run_tests
from cascade.task.incident_budget import (
    POLICY_VERSION,
    bind_incident_budget,
    read_incident_budget,
    reserve_incident_operation,
    settle_incident_operation,
)
from cascade.task_rollup import retry_pending_task_merges
from cascade.task.worktree import clear_task_runs, get_task_run
from cascade.team_supervision import request_feature_review_repair
from cascade.tracking import MergeRequest
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.watchdog.events import read_events
from cascade.workspace.integration_worktree import get_integration_worktree
from cascade.workspace.source_fingerprint import source_fingerprint
from cascade.workspace.types import ProjectContext
from tests.feature.test_recovery import _select_roles
from tests.support import add_doc, approve_board_feature, make_repo
from tests.test_approval_selection_gate import _inventory


@pytest.fixture(autouse=True)
def _provider_and_task_isolation(monkeypatch: pytest.MonkeyPatch):
    inventory = _inventory("offered")
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    monkeypatch.setattr(
        "cascade.agent.selection_preflight.probe_provider_compatibility",
        lambda _provider: ProviderCompatibilityEvidence(True, True, True),
    )
    clear_task_runs()
    set_project_context(None)
    yield
    clear_task_runs()
    set_project_context(None)


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _signed_runtime_receipt(
    path: Path,
    *,
    key: bytes,
    reviewed: Path,
    reviewed_revision: str,
    integrated: Path,
    integrated_revision: str,
    review_url: str,
) -> None:
    value: dict[str, object] = {
        "version": 1,
        "accepted_review_url": review_url,
        "authorized_actor": "release-operator@example.test",
        "environment": "late-repair-integration",
        "reviewed_repository": str(reviewed.resolve()),
        "reviewed_revision": reviewed_revision,
        "integrated_repository": str(integrated.resolve()),
        "integrated_revision": integrated_revision,
        "installed_source_sha256": source_fingerprint(reviewed / "cascade"),
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["receipt_id"] = hashlib.sha256(canonical).hexdigest()
    signed = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["signature"] = hmac.new(key, signed, hashlib.sha256).hexdigest()
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _completed_feature(
    tmp_path: Path, *, role_skills: bool = False
) -> tuple[Path, object, str]:
    """Run the normal mint, dispatch, validation, and queued-delivery path."""

    root = make_repo(tmp_path, role_skills=role_skills)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_roles(
        root,
        "epic_001",
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    )
    _select_roles(root, "feat_001", "feature_lead", "feature_architect", "swe")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    feature_entry = get_integration_worktree(root, "feature", "feat_001")
    assert feature_entry is not None

    task_id = mint_task(
        "Deliver value",
        body_stub="Implement and validate product.py.",
        feature_id="feat_001",
        root=root,
    )
    assert dispatch_task(task_id, "human", root=root).ok
    run = get_task_run(task_id)
    assert run is not None
    (run.worktree / "product.py").write_text("VALUE = 1\n", encoding="utf-8")
    (run.worktree / "test_product.py").write_text(
        "from product import VALUE\n\ndef test_value():\n    assert VALUE == 1\n",
        encoding="utf-8",
    )
    (run.worktree / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n", encoding="utf-8"
    )
    swe_commit("implement value", task_id=task_id, task_run=run, root=root)
    validation = swe_run_tests(
        cmd=["pytest", "test_product.py", "-q"],
        task_id=task_id,
        task_run=run,
        root=root,
    )
    assert validation["exit_code"] == 0
    assert validation["final_validation"]["task_id"] == task_id
    assert merge_task_branch(task_id, root=root).ok
    write_closeout(
        "feat_001",
        "Implemented product.py through the supervised Task delivery path.",
        root=feature_entry.path,
    )
    return root, feature_entry, task_id


class DeterministicForge:
    """Contract-shaped forge boundary with observable publication count."""

    def __init__(
        self,
        historical: MergeRequest,
        state: str,
        *,
        historical_is_current: bool = False,
    ) -> None:
        self.historical = historical
        self.state = state
        self.historical_is_current = historical_is_current
        self.created: list[MergeRequest] = []
        self.current_source_head: str | None = None
        self.current_target_head: str | None = None
        self.current_merge_sha: str | None = None
        self.current_state = "open"
        self.comments: list[dict[str, object]] = []
        self.required_check_policy: dict[str, object] | None = None
        self.required_check_results: dict[str, object] | None = None

    def snapshot(self, _root: Path, mr: MergeRequest) -> dict[str, object]:
        current = bool(
            (self.created and mr == self.created[0])
            or (not self.created and self.historical_is_current and mr == self.historical)
        )
        assert current or mr == self.historical
        snapshot: dict[str, object] = {
            "state": self.current_state if current else self.state,
            "url": mr.url,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "source_revision": self.current_source_head or "historical-source",
            "target_revision": (
                self.current_target_head if current else "historical-target"
            ),
            "merge_sha": (
                self.current_merge_sha if current and self.current_state == "merged" else
                "historical-merge" if not current and self.state == "merged" else None
            ),
            "comments": list(self.comments),
        }
        if current and self.required_check_policy is not None:
            snapshot["required_check_policy"] = self.required_check_policy
        if current and self.required_check_results is not None:
            snapshot["required_check_results"] = self.required_check_results
        return snapshot

    def find(self, *_args, **_kwargs) -> MergeRequest | None:
        return self.created[0] if self.created else None

    def create(self, _root: Path, **kwargs: object) -> MergeRequest:
        created = MergeRequest(
            url="https://forge.example/pulls/repair",
            number="2",
            forge="github",
            source_branch=str(kwargs["source_branch"]),
            target_branch=str(kwargs["target_branch"]),
            draft=False,
        )
        self.created.append(created)
        return created


def _assert_same_incident_budget(
    original: dict[str, object], current: dict[str, object]
) -> None:
    """Check immutable allowance identity and monotonic public accounting."""

    for key in (
        "incident_id",
        "original_action_id",
        "original_admitted_at",
        "policy",
        "accountable_owner",
        "bindings",
    ):
        assert current[key] == original[key]
    limits = dict(dict(current["policy"])["limits"])
    assert limits and all(
        isinstance(value, int) and value > 0 for value in limits.values()
    )
    original_charged = dict(original["charged"])
    current_charged = dict(current["charged"])
    assert all(current_charged[key] >= original_charged[key] for key in original_charged)
    assert set(dict(original["operations"])) <= set(dict(current["operations"]))


def test_parent_requested_open_review_repair_reuses_identity_until_verified_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Follow one real Feature repair from parent request through retirement.

    Git repositories, queue/checkpoint delivery, Task tools, publication,
    merge observation, and the independent postcheck are production code.  The
    only scripted seams are planning/SWE provider output and forge/check
    transport.
    """

    from cascade.feature.checkpoint import thread_config as feature_thread_config
    from cascade.feature.graph import clear_feature_graph_sessions, ensure_feature_graph
    from cascade.feature.repair import feature_repair_actions
    from cascade.task import invoke_tool
    from cascade.task.graph import set_task_run_role_fn
    from cascade.watchdog.incident_postcheck import reconcile_open_review_repair
    from cascade.workspace.kickoff import deferred_kickoffs, wait_for_background_kickoffs
    from cascade.workspace.integration_worktree import retire_terminal_registered_worktrees

    root, feature_entry, original_task_id = _completed_feature(
        tmp_path, role_skills=True
    )
    exclude = root / ".git" / "info" / "exclude"
    exclude.write_text(
        exclude.read_text(encoding="utf-8")
        + ".cascade/\ndocs/_comments/\ndocs/_queue/\ndocs/_war_room/\n"
    )
    epic_entry = get_integration_worktree(root, "epic", "epic_001")
    assert epic_entry is not None
    remote = tmp_path / "review-remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "HEAD:main")
    _git(epic_entry.path, "push", "-u", "origin", "epic/epic_001")
    move_doc("feat_001", "completed", root=feature_entry.path)
    original_source = _git(feature_entry.path, "rev-parse", "HEAD")
    original_target = _git(epic_entry.path, "rev-parse", "HEAD")
    original_review = MergeRequest(
        "https://forge.example/pulls/original",
        "1",
        "github",
        "feat/feat_001",
        "epic/epic_001",
        False,
    )
    review._store_review_generation(
        root,
        "feat_001",
        {
            "url": original_review.url,
            "number": original_review.number,
            "forge": original_review.forge,
            "source_branch": original_review.source_branch,
            "target_branch": original_review.target_branch,
            "source_head": original_source,
            "target_head": original_target,
            "draft": False,
            "closed": False,
            "state": "open",
            "seen_comments": ["review-thread-7"],
            "toast_notified": True,
        },
        generation=0,
        action_id=None,
    )
    provider_turns: list[str] = []

    async def scripted_planning_provider(role: str, *_args: object, **_kwargs: object) -> str:
        provider_turns.append(role)
        return f"{role} acknowledged the durable repair request"

    clear_feature_graph_sessions()
    monkeypatch.setattr(
        "cascade.feature.graph.run_planning_role_turn", scripted_planning_provider
    )
    request = {
        "reason": "Repair the current failed check without replacing the review",
        "evidence": {"comment_id": "review-thread-7", "check": "product"},
        "approval_reference": "approved-feature-plan",
        "scope_reference": "review-comment:review-thread-7",
        "review_url": original_review.url,
        "review_forge": original_review.forge,
        "source_ref": original_review.source_branch,
        "target_ref": original_review.target_branch,
        "observed_source_head": original_source,
        "observed_target_head": original_target,
        "observed_review_generation": 0,
    }
    admitted = request_feature_review_repair(
        "feat_001",
        "review-fix:thread-7",
        root=root,
        requesting_parent_id="epic_001",
        **request,
    )
    assert admitted["admitted"] is True
    assert admitted["wakeup_acknowledged"] is True
    assert admitted["verified"] is False
    assert provider_turns == ["feature_lead", "feature_architect"]
    checkpoint_after_admission = ensure_feature_graph("feat_001", root=root).get_state(
        feature_thread_config("feat_001")
    )
    admitted_history = list((checkpoint_after_admission.values or {}).get("messages", []))

    replay = request_feature_review_repair(
        "feat_001",
        "review-fix:thread-7",
        root=root,
        requesting_parent_id="epic_001",
        **request,
    )
    assert replay["action_id"] == admitted["action_id"]
    assert replay["generation"] == admitted["generation"] == 1
    assert provider_turns == ["feature_lead", "feature_architect"]
    checkpoint = ensure_feature_graph("feat_001", root=root).get_state(
        feature_thread_config("feat_001")
    )
    assert list((checkpoint.values or {}).get("messages", [])) == admitted_history

    def mint_repair() -> str:
        return mint_task(
            "Repair current review checks",
            body_stub="Change product.py to VALUE = 2 and validate test_product.py.",
            repair_request_id="review-fix:thread-7",
            feature_id="feat_001",
            root=root,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        repair_task_ids = list(pool.map(lambda _index: mint_repair(), range(2)))
    assert repair_task_ids[0] == repair_task_ids[1]
    repair_task_id = repair_task_ids[0]
    feature = read_doc("feat_001", root=feature_entry.path)
    assert feature.meta.children.count(repair_task_id) == 1
    assert original_task_id in feature.meta.children

    validations: list[dict[str, object]] = []
    physical_task_turns: list[str] = []

    async def scripted_swe_provider(_turn: object) -> RoleResult:
        physical_task_turns.append(repair_task_id)
        invoke_tool(
            repair_task_id,
            "swe_write",
            {
                "path": "test_product.py",
                "content": "from product import VALUE\n\ndef test_value():\n    assert VALUE == 2\n",
            },
            root=root,
            feature_id="feat_001",
        )
        invoke_tool(
            repair_task_id,
            "swe_commit",
            {"message": "add current repair check"},
            root=root,
            feature_id="feat_001",
        )
        red = invoke_tool(
            repair_task_id,
            "swe_run_tests",
            {"cmd": ["pytest", "test_product.py", "-q"]},
            root=root,
            feature_id="feat_001",
        )
        validations.append(red)
        assert red["exit_code"] == 1
        invoke_tool(
            repair_task_id,
            "swe_write",
            {"path": "product.py", "content": "VALUE = 2  # repaired review\n"},
            root=root,
            feature_id="feat_001",
        )
        invoke_tool(
            repair_task_id,
            "swe_commit",
            {"message": "repair current review check"},
            root=root,
            feature_id="feat_001",
        )
        green = invoke_tool(
            repair_task_id,
            "swe_run_tests",
            {"cmd": ["pytest", "test_product.py", "-q"]},
            root=root,
            feature_id="feat_001",
        )
        validations.append(green)
        assert green["exit_code"] == 0
        return RoleResult(text="repair committed and validated", status="finished")

    from cascade.task import boot, wiring, worktree
    from cascade.watchdog import hooks

    monkeypatch.setitem(hooks._boot, "task", [])
    monkeypatch.setitem(hooks._teardown, "task", [])
    monkeypatch.setattr(boot, "_boot_root", None)
    monkeypatch.setattr(wiring, "_wiring_root", None)
    monkeypatch.setattr(worktree, "_root", None)
    wiring.install_task_wiring(root)
    set_task_run_role_fn(scripted_swe_provider)
    with deferred_kickoffs():
        assert dispatch_task(repair_task_id, "human", root=root).ok
        repair_run = get_task_run(repair_task_id)
        assert repair_run is not None and repair_run.state != "booting"
    assert wait_for_background_kickoffs(20)
    if physical_task_turns != [repair_task_id]:
        from cascade.task.execution import execution_view

        pytest.fail(
            repr(
                {
                    "run": repair_run,
                    "execution": execution_view(repair_task_id, root=root),
                    "events": read_events(repair_task_id, 0, root=root)[0],
                }
            )
        )
    assert [row["exit_code"] for row in validations] == [1, 0]
    old_validation = validations[0]["final_validation"]
    current_validation = validations[1]["final_validation"]
    assert old_validation["deliverable_sha"] != current_validation["deliverable_sha"]
    assert merge_task_branch(repair_task_id, root=root).ok

    repair_action = current_feature_repair_record("feat_001", root=root)
    assert repair_action is not None
    assert repair_action["action_id"] == admitted["action_id"]
    assert repair_action["reserved_task_id"] == repair_task_id
    assert repair_action["final_validation"] == current_validation
    assert repair_action["approval_reference"] == "approved-feature-plan"

    forge = DeterministicForge(
        original_review, "open", historical_is_current=True
    )
    forge.current_source_head = original_source
    forge.current_target_head = original_target
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    monkeypatch.setattr(review, "merge_request_snapshot", forge.snapshot)
    monkeypatch.setattr("cascade.tracking.merge_request_snapshot", forge.snapshot)
    monkeypatch.setattr(review, "find_merge_request", forge.find)
    monkeypatch.setattr(review, "create_merge_request", forge.create)
    published = review.ensure_feature_review("feat_001", root=root)
    assert published is not None and published.url == original_review.url
    current_review = review.review_record_for_feature("feat_001", root=root)
    assert current_review is not None
    corrected_source = str(current_review["source_head"])
    assert corrected_source != original_source
    assert current_review["action_id"] == admitted["action_id"]
    assert len(forge.created) == 0
    forge.comments = [
        {
            "id": "review-thread-7",
            "body": "Keep this review discussion attached to the original PR.",
            "author": {"login": "reviewer"},
        }
    ]
    review.poll_feature_reviews(root)
    current_review = review.review_record_for_feature("feat_001", root=root)
    assert current_review is not None
    assert current_review["seen_comments"] == ["review-thread-7"]

    forge.current_source_head = corrected_source
    forge.required_check_policy = {
        "available": True,
        "source_head": original_source,
        "target_head": original_target,
        "required": ["product"],
    }
    forge.required_check_results = {
        "available": True,
        "source_head": original_source,
        "target_head": original_target,
        "statuses": {"product": "success"},
        "checks": {
            "product": {
                "status": "success",
                "source_head": original_source,
                "generation": 1,
            }
        },
    }
    stale = reconcile_open_review_repair("feat_001", root=root)
    assert stale["verified"] is False
    assert stale["reason"] == "required_check_policy_stale"

    _git(epic_entry.path, "merge", "--no-ff", corrected_source, "-m", "merge repaired review")
    forge.current_state = "merged"
    forge.current_merge_sha = _git(epic_entry.path, "rev-parse", "HEAD")
    forge.current_target_head = forge.current_merge_sha
    forge.required_check_policy = {
        "available": True,
        "source_head": corrected_source,
        "target_head": forge.current_target_head,
        "required": ["product"],
    }
    forge.required_check_results = {
        "available": True,
        "source_head": corrected_source,
        "target_head": forge.current_target_head,
        "statuses": {"product": "success"},
        "checks": {
            "product": {
                "status": "success",
                "source_head": corrected_source,
                "generation": 2,
            }
        },
    }
    _git(epic_entry.path, "push", "origin", "epic/epic_001")
    assert _git(epic_entry.path, "status", "--porcelain") == ""
    # The first forge observation persists acceptance.  That write is not
    # retroactive authority for the postcheck that preceded it.
    assert review.reconcile_feature_review_completions(root) == []
    accepted_pending = review.review_record_for_feature("feat_001", root=root)
    assert accepted_pending is not None and accepted_pending["closed"] is True
    # Acceptance synchronization may add the completed lifecycle copy on the
    # intended target.  The next forge/check observation names that current
    # target while retaining the human-accepted merge object.
    forge.current_target_head = _git(epic_entry.path, "rev-parse", "HEAD")
    forge.required_check_policy["target_head"] = forge.current_target_head
    forge.required_check_results["target_head"] = forge.current_target_head
    _git(epic_entry.path, "push", "origin", "epic/epic_001")
    verified = reconcile_open_review_repair("feat_001", root=root)
    assert verified["verified"] is True, verified
    assert verified["repair_action_id"] == admitted["action_id"]
    assert verified["checked_source_head"] == corrected_source
    assert verified["target_head"] == forge.current_target_head
    assert review.reconcile_feature_review_completions(root) == ["feat_001"]

    retire_terminal_registered_worktrees(root)
    assert get_integration_worktree(root, "feature", "feat_001") is None
    assert len(feature_repair_actions("feat_001", root=root)) == 1
    assert current_feature_repair_record("feat_001", root=root) is None
    accepted = review.review_record_for_feature("feat_001", root=root)
    assert accepted is not None and accepted["closed"] is True
    assert accepted["url"] == original_review.url
    assert accepted["seen_comments"] == ["review-thread-7"]
    assert provider_turns == ["feature_lead", "feature_architect"]
    assert physical_task_turns == [repair_task_id]


@pytest.mark.parametrize("split_roots", [True, False], ids=["split-roots", "colocated"])
def test_watchdog_owner_repair_delivers_and_independently_verifies_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, split_roots: bool
) -> None:
    """Join the production queue, owner tools, publication, and postcheck."""

    from cascade.feature.recovery import recover_task
    from cascade.review import reconcile_feature_review_completions
    from cascade.task.action_recovery import load_action
    from cascade.watchdog.audit_recovery import dispatch_audit_recovery
    from cascade.watchdog.incident_postcheck import reconcile_parent_lifecycle_incident

    root = make_repo(tmp_path / "product", role_skills=True)
    tracking = make_repo(tmp_path / "tracking") if split_roots else root
    if split_roots:
        set_project_context(ProjectContext.split(root, tracking))
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(
        source / "cascade",
        root / "cascade",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    config = "[automation]\nenabled = false\npoll_seconds = 999\n"
    if split_roots:
        config = f'tracking_repository = {json.dumps(str(tracking))}\n' + config
    (root / "cascade.toml").write_text(config, encoding="utf-8")
    _git(root, "add", "cascade", "cascade.toml", "skills")
    _git(root, "commit", "-m", "seed production recovery source")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    push_log = tmp_path / f"pushes-{'split' if split_roots else 'colocated'}.jsonl"
    push_hook = remote / "hooks" / "post-receive"
    push_hook.write_text(
        "#!/bin/sh\nwhile read old new ref; do "
        f'printf "%s %s %s\\n" "$old" "$new" "$ref" >> "{push_log}"; '
        "done\n",
        encoding="utf-8",
    )
    push_hook.chmod(0o755)
    _git(root, "remote", "add", "origin", str(remote))
    (root / ".git/info/exclude").write_text(
        ".cascade/\ndocs/_queue/\ndocs/_war_room/\n", encoding="utf-8"
    )
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    epic_doc = read_doc("epic_001", root=root)
    epic_doc.meta.children.append("feat_001")
    write_doc(epic_doc, root=root)
    feature_doc = read_doc("feat_001", root=root)
    feature_doc.body += (
        "\n## Closeout\n\nThe repaired product is covered by its real validator.\n"
    )
    write_doc(feature_doc, root=root)
    _select_roles(
        root, "epic_001", "epic_manager", "epic_architect", "feature_lead",
        "feature_architect", "swe",
    )
    _select_roles(root, "feat_001", "feature_lead", "feature_architect", "swe")
    if split_roots:
        # Product history retains the reviewed brief used to cut integration
        # branches; the distinct tracking checkout remains the mutation owner.
        shutil.copytree(tracking / "docs", root / "docs", dirs_exist_ok=True)
        _git(root, "add", "docs")
        _git(root, "commit", "-m", "bind reviewed tracking briefs to product base")
    _git(root, "push", "-u", "origin", "HEAD:main")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    feature_entry = get_integration_worktree(root, "feature", "feat_001")
    epic_entry = get_integration_worktree(root, "epic", "epic_001")
    assert feature_entry is not None and epic_entry is not None

    task_id = mint_task(
        "Repair the product", body_stub="Repair and validate product.py.",
        feature_id="feat_001", root=root,
    )
    from cascade.task import invoke_tool

    physical_turns: list[str] = []
    task_validations: list[dict[str, object]] = []
    repaired_adapter = (
        source / "cascade" / "feature" / "recovery.py"
    ).read_text(encoding="utf-8") + "\n# reviewed late-repair adapter revision\n"

    async def scripted_provider(_turn: object) -> RoleResult:
        physical_turns.append(task_id)
        for path, content in (
            ("product.py", "VALUE = 0\n"),
            ("test_product.py", "from product import VALUE\n\ndef test_value():\n    assert VALUE == 1\n"),
            ("cascade/feature/recovery.py", repaired_adapter),
            (".gitignore", "__pycache__/\n.pytest_cache/\n"),
        ):
            invoke_tool(
                task_id, "swe_write", {"path": path, "content": content},
                root=root, feature_id="feat_001",
            )
        invoke_tool(
            task_id, "swe_commit", {"message": "retain the real failing repair"},
            root=root, feature_id="feat_001",
        )
        red = invoke_tool(
            task_id, "swe_run_tests", {"cmd": ["pytest", "test_product.py", "-q"]},
            root=root, feature_id="feat_001",
        )
        task_validations.append(red)
        assert red["exit_code"] == 1 and "assert 0 == 1" in red["output"], red["output"]
        # CPython's timestamp-based bytecode cache uses whole seconds and size.
        # A same-size edit on a fast runner can otherwise reuse the red module.
        invoke_tool(
            task_id, "swe_write", {"path": "product.py", "content": "VALUE = 1  # repaired\n"},
            root=root, feature_id="feat_001",
        )
        invoke_tool(
            task_id, "swe_commit", {"message": "repair the product"},
            root=root, feature_id="feat_001",
        )
        green = invoke_tool(
            task_id, "swe_run_tests", {"cmd": ["pytest", "test_product.py", "-q"]},
            root=root, feature_id="feat_001",
        )
        task_validations.append(green)
        assert green["exit_code"] == 0, green["output"]
        assert green["final_validation"]["task_id"] == task_id
        return RoleResult(text="repair tested and queued", status="finished")

    from cascade.task.graph import set_task_run_role_fn
    from cascade.workspace.kickoff import (
        deferred_kickoffs,
        wait_for_background_kickoffs,
    )

    # Production dispatch creates a booting worktree and only the wired boot
    # hooks may transition it to coding. Install the same hooks as the worker;
    # a scripted provider does not authorize bypassing boot or skill loading.
    from cascade.task import boot, wiring, worktree
    from cascade.watchdog import hooks

    monkeypatch.setitem(hooks._boot, "task", [])
    monkeypatch.setitem(hooks._teardown, "task", [])
    monkeypatch.setattr(boot, "_boot_root", None)
    monkeypatch.setattr(wiring, "_wiring_root", None)
    monkeypatch.setattr(worktree, "_root", None)
    wiring.install_task_wiring(root)
    set_task_run_role_fn(scripted_provider)
    with deferred_kickoffs():
        assert dispatch_task(task_id, "human", root=root).ok
        run = get_task_run(task_id)
        assert run is not None and run.state != "booting"
    assert wait_for_background_kickoffs(10)
    assert physical_turns == [task_id]
    assert [result["exit_code"] for result in task_validations] == [1, 0]
    red_target = task_validations[0]["final_validation"]
    green_target = task_validations[1]["final_validation"]
    assert isinstance(red_target, dict) and isinstance(green_target, dict)
    assert red_target["deliverable_sha"] != green_target["deliverable_sha"]
    completed_task_run = get_task_run(task_id)
    assert completed_task_run is not None
    assert green_target["deliverable_sha"] == _git(
        completed_task_run.worktree, "rev-parse", "HEAD"
    )
    assert green_target["feature_base_sha"] == red_target["feature_base_sha"]
    if split_roots and get_integration_worktree(root, "epic", "epic_001") is None:
        from cascade.workspace.integration_worktree import repair_missing_worktree

        restored_epic = repair_missing_worktree("epic", "epic_001", trunk=root)
        assert restored_epic is not None
        epic_entry = restored_epic

    # Reproduce the admitted obligation after the Task has queued green
    # delivery, but before the supervisor consumes it. Move the parent only
    # after the asynchronous boot/turn has finished; do not race board reads.
    move_doc("feat_001", "completed", root=feature_entry.path)
    from cascade.boss.rollup import _emit_feature_completed

    if not split_roots:
        _emit_feature_completed("feat_001", "epic_001", root)

    from cascade.task.action_recovery import resume_action
    from cascade.task_rollup import _resume_queued_merge

    refused = resume_action(
        f"{task_id}:queued_merge", root=root,
        execute=lambda _context: _resume_queued_merge(task_id, root),
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert refused["failure_classification"] == "parent_lifecycle_mismatch"
    queued = load_action(f"{task_id}:queued_merge", root=root)
    mismatch = queued["metadata"]["parent_lifecycle_mismatch"]
    mismatch_generation = mismatch["authoritative_generation"]
    original_incident_id = f"{task_id}:queued_merge"
    budget_generation = queued["incident"]["authoritative_generation"]
    bound_budget = bind_incident_budget(
        original_incident_id,
        original_incident_id,
        budget_generation,
        {"policy_version": POLICY_VERSION},
        root=root,
    )
    assert bound_budget["incident_id"] == original_incident_id
    assert bound_budget["original_action_id"] == original_incident_id

    from cascade.watchdog.audit import project_audit_observation

    first_observation = project_audit_observation(
        task_id, root=root, monotonic=lambda: 0.0
    )
    assert first_observation.classification == "proven_incident"
    assert dispatch_audit_recovery(root, task_id, timeout_seconds=10)
    repair_incident = next(
        row["incident"]
        for row in recovery_actions(root=root)
        if row.get("incident", {}).get("work_id") == task_id
        and row.get("incident", {}).get("failure_class")
        == "parent_lifecycle_mismatch"
    )
    incident_generation = repair_incident["authoritative_generation"]
    assert repair_incident["original_incident_id"] == original_incident_id
    adapter_budget = read_incident_budget(original_incident_id, root=root)
    assert adapter_budget is not None
    _assert_same_incident_budget(bound_budget, adapter_budget)
    assert adapter_budget["charged"]["tool_attempts"] == 1
    assert len(adapter_budget["operations"]) == 1
    owner_result = recover_task(
        task_id,
        feature_id="feat_001",
        root=root,
        expected_generation=mismatch_generation,
    )
    assert owner_result["executed"] is False
    assert owner_result["refusal"]["code"] in {
        "incident_no_longer_matches", "authoritative_generation_changed"
    }
    delivered = resume_action(
        f"{task_id}:queued_merge", root=root,
        execute=lambda _context: _resume_queued_merge(task_id, root),
    )
    assert delivered["recovery_state"] == "completed"
    forge = DeterministicForge(
        MergeRequest("https://forge.example/pulls/old", "0", "github",
                     "feat/feat_001", "epic/epic_001", False),
        "open",
    )
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    monkeypatch.setattr(review, "merge_request_snapshot", forge.snapshot)
    monkeypatch.setattr(review, "find_merge_request", forge.find)
    monkeypatch.setattr(review, "create_merge_request", forge.create)
    from cascade.boss.rollup import try_complete_feature

    if get_integration_worktree(root, "epic", "epic_001") is None:
        from cascade.workspace.integration_worktree import repair_missing_worktree

        restored_epic = repair_missing_worktree("epic", "epic_001", trunk=root)
        assert restored_epic is not None
        epic_entry = restored_epic

    # Reserve the expensive owner operation before entering the production
    # publication path. The first process dies after the remote and forge
    # accept the exact publication but before its local generation is stored.
    publication_operation = f"publication:{task_id}:{incident_generation}"
    publication_claim = f"publication-claim:{incident_generation}"
    publication_permit = reserve_incident_operation(
        original_incident_id,
        publication_operation,
        "feature_review_reconciliation",
        {"tool_attempts": 1},
        publication_claim,
        POLICY_VERSION,
        root=root,
    )
    assert publication_permit.admitted
    reserved_budget = read_incident_budget(original_incident_id, root=root)
    assert reserved_budget is not None
    assert reserved_budget["operations"][publication_operation]["state"] == "reserved"

    real_store_review_generation = review._store_review_generation
    interrupt_receipt = True

    def fail_before_local_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal interrupt_receipt
        if interrupt_receipt:
            interrupt_receipt = False
            raise OSError("post-push publication receipt interruption")
        return real_store_review_generation(*args, **kwargs)

    monkeypatch.setattr(review, "_store_review_generation", fail_before_local_receipt)
    with pytest.raises(OSError, match="post-push publication receipt interruption"):
        try_complete_feature("feat_001", root=root)
    assert interrupt_receipt is False
    interrupted_source_head = _git(
        root, "ls-remote", "origin", "refs/heads/feat/feat_001"
    ).split()[0]
    assert interrupted_source_head == _git(feature_entry.path, "rev-parse", "HEAD")
    forge.current_source_head = interrupted_source_head
    forge.current_target_head = _git(epic_entry.path, "rev-parse", "HEAD")
    authoritative_forge = forge.snapshot(root, forge.created[0])
    assert authoritative_forge["state"] == "open"
    assert authoritative_forge["source_revision"] == interrupted_source_head
    assert authoritative_forge["target_revision"] == forge.current_target_head
    assert review.review_record_for_feature("feat_001", root=root) is None

    # Unavailable forge evidence cannot turn the remote effect into a receipt
    # or trigger a replacement review.
    # The original incident retains its accountable owner and next capability.
    def unavailable_find(*_args: object, **_kwargs: object) -> MergeRequest | None:
        raise GitError("authoritative forge evidence unavailable")

    monkeypatch.setattr(review, "find_merge_request", unavailable_find)
    with pytest.raises(GitError, match="authoritative forge evidence unavailable"):
        try_complete_feature("feat_001", root=root)
    still_pending = next(
        row["incident"]
        for row in recovery_actions(root=root)
        if row.get("incident", {}).get("work_id") == task_id
        and row.get("incident", {}).get("authoritative_generation")
        == incident_generation
    )
    assert still_pending["outcome"] != "success"
    assert still_pending["accountable_owner"]
    assert still_pending["selected_capability"]
    assert review.review_record_for_feature("feat_001", root=root) is None
    assert len(forge.created) == 1
    monkeypatch.setattr(review, "find_merge_request", forge.find)

    forge.current_source_head = "changed-authoritative-source"
    with pytest.raises(GitError, match="review route conflicts"):
        try_complete_feature("feat_001", root=root)
    assert review.review_record_for_feature("feat_001", root=root) is None
    assert len(forge.created) == 1
    forge.current_source_head = interrupted_source_head

    settled_publication = settle_incident_operation(
        original_incident_id,
        publication_operation,
        {
            "outcome": "success",
            "quality": "known",
            "usage": {"tool_attempts": 1},
            "claim_complete": True,
        },
        root=root,
    )
    assert settled_publication.admitted
    assert reserve_incident_operation(
        original_incident_id,
        publication_operation,
        "feature_review_reconciliation",
        {"tool_attempts": 1},
        publication_claim,
        POLICY_VERSION,
        root=root,
    ).reason == "operation_identity_replayed"
    assert settle_incident_operation(
        original_incident_id,
        publication_operation,
        {"outcome": "success", "quality": "known", "usage": {}},
        root=root,
    ).reason == "operation_already_settled"
    # Competing owner callers reuse the authoritative remote/forge effects and
    # persist one immutable review generation without another publication.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda _index: try_complete_feature("feat_001", root=root), range(2)
            )
        )
    assert len(forge.created) == 1
    record = review.review_record_for_feature("feat_001", root=root)
    assert record is not None
    assert record["source_head"] == interrupted_source_head
    publication_pushes = push_log.read_text(encoding="utf-8").splitlines()
    assert sum(
        line.split()[1] == interrupted_source_head
        and line.split()[2] == "refs/heads/feat/feat_001"
        for line in publication_pushes
    ) == 1
    remote_reconciled_budget = read_incident_budget(original_incident_id, root=root)
    assert remote_reconciled_budget is not None
    _assert_same_incident_budget(adapter_budget, remote_reconciled_budget)
    assert remote_reconciled_budget["charged"]["tool_attempts"] == 2
    assert len(remote_reconciled_budget["operations"]) == 2

    forge.current_state = "merged"
    _git(
        epic_entry.path,
        "merge",
        "--no-ff",
        str(record["source_head"]),
        "-m",
        "integrate repair",
    )
    forge.current_merge_sha = _git(epic_entry.path, "rev-parse", "HEAD")
    _git(epic_entry.path, "push", "origin", "epic/epic_001")

    # A pre-existing premature completion event cannot substitute for closing
    # the accepted target copy; repeated reconciliation is effect-idempotent.
    reconcile_feature_review_completions(root)
    pushes_after_acceptance = push_log.read_text(encoding="utf-8").splitlines()
    reconcile_feature_review_completions(root)
    reconcile_feature_review_completions(root)
    assert push_log.read_text(encoding="utf-8").splitlines() == pushes_after_acceptance
    from cascade.workspace.integration_worktree import (
        retire_terminal_registered_worktrees,
    )

    retire_terminal_registered_worktrees(root)
    retire_terminal_registered_worktrees(root)
    from cascade.task.worktree import remove_task_worktree

    completed_run = get_task_run(task_id)
    if completed_run is not None and completed_run.worktree.is_dir():
        remove_task_worktree(completed_run, root=root)
    assert not completed_task_run.worktree.exists()
    assert get_integration_worktree(root, "task", task_id) is None
    accepted = review.review_record_for_feature("feat_001", root=root)
    assert accepted is not None
    assert accepted["closed"] is True
    assert accepted["accepted_source_head"] == record["source_head"]
    assert accepted["accepted_merge_sha"] == forge.current_merge_sha

    # Review validation, delivery, and retirement are still insufficient while
    # the accepted recovery adapter is not loaded by an independently verified
    # worker.  The original incident must remain the current candidate.
    pending_runtime = reconcile_parent_lifecycle_incident(
        task_id, incident_generation, root=root
    )
    assert pending_runtime["verified"] is False
    assert pending_runtime["reason"] == "pending:loaded_runtime_current"

    reviewed = tmp_path / f"reviewed-{'split' if split_roots else 'colocated'}"
    integrated = tmp_path / f"integrated-{'split' if split_roots else 'colocated'}"
    _git(root, "worktree", "add", "--detach", str(reviewed), str(record["source_head"]))
    _git(root, "worktree", "add", "--detach", str(integrated), str(forge.current_merge_sha))
    assert "reviewed late-repair adapter revision" in (
        reviewed / "cascade" / "feature" / "recovery.py"
    ).read_text(encoding="utf-8")
    key = b"late-repair-runtime-authority-key-32-bytes"
    key_path = tmp_path / f"authority-{'split' if split_roots else 'colocated'}.key"
    receipt = tmp_path / f"deployment-{'split' if split_roots else 'colocated'}.json"
    manifest = tmp_path / f"manifest-{'split' if split_roots else 'colocated'}.json"
    key_path.write_bytes(key)
    _signed_runtime_receipt(
        receipt,
        key=key,
        reviewed=reviewed,
        reviewed_revision=str(record["source_head"]),
        integrated=integrated,
        integrated_revision=str(forge.current_merge_sha),
        review_url=str(accepted["url"]),
    )
    bootstrap = subprocess.run(
        [
            sys.executable,
            "-m",
            "cascade.cli",
            "runtime-bootstrap",
            "--reviewed-source",
            str(reviewed),
            "--integrated-source",
            str(integrated),
            "--deployment-receipt",
            str(receipt),
            "--authority-key",
            str(key_path),
            "--output",
            str(manifest),
        ],
        cwd=reviewed,
        env={**os.environ, "PYTHONPATH": str(reviewed)},
        capture_output=True,
        text=True,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    bootstrap_budget = read_incident_budget(original_incident_id, root=root)
    assert bootstrap_budget is not None
    _assert_same_incident_budget(remote_reconciled_budget, bootstrap_budget)
    assert bootstrap_budget["charged"]["tool_attempts"] == 2

    from tests.harness.cascade_up_subprocess import (
        free_port,
        get_supervisor_health,
        poll_until,
        wait_for_http,
        worker_pid_for_launcher,
    )

    port = free_port()
    launcher = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "cascade.cli",
            "up",
            "--root",
            str(root),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--runtime-authority",
            str(manifest),
            "--runtime-authority-key",
            str(key_path),
        ],
        cwd=reviewed,
        env={
            **os.environ,
            "PYTHONPATH": str(reviewed),
            "CASCADE_ENABLE_FAKE_PROVIDER": "1",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    worker_starts: list[int] = []
    try:
        base = f"http://127.0.0.1:{port}"
        wait_for_http(f"{base}/api/health")

        def runtime_identity() -> dict[str, object]:
            status, health = get_supervisor_health(base)
            if status != 200 or not health:
                return {}
            value = health.get("runtime_identity")
            return value if isinstance(value, dict) else {}

        poll_until(lambda: runtime_identity().get("verified") is True)
        first_pid = worker_pid_for_launcher(launcher.pid)
        assert first_pid is not None
        worker_starts.append(first_pid)
        os.kill(first_pid, signal.SIGKILL)
        poll_until(
            lambda: runtime_identity().get("verified") is True
            and runtime_identity().get("worker_pid") != first_pid,
            timeout=60,
        )
        restarted = runtime_identity()
        worker_starts.append(int(restarted["worker_pid"]))
        assert restarted["reviewed_revision"] == record["source_head"]
        assert restarted["integrated_revision"] == forge.current_merge_sha
        assert restarted["accepted_review_url"] == accepted["url"]
        assert restarted["capability_generation"]
        loaded_recovery = restarted["loaded_modules"]["cascade.feature.recovery"]
        assert Path(loaded_recovery["origin"]).resolve() == (
            reviewed / "cascade" / "feature" / "recovery.py"
        ).resolve()
        restarted_budget = read_incident_budget(original_incident_id, root=root)
        assert restarted_budget is not None
        _assert_same_incident_budget(bootstrap_budget, restarted_budget)
        assert restarted_budget["charged"]["tool_attempts"] == 2

        # The worker recovery lane and two callers may all observe the same
        # candidate.  The lifecycle fence permits exactly one terminal receipt.
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = list(
                pool.map(
                    lambda _index: reconcile_parent_lifecycle_incident(
                        task_id, incident_generation, root=root
                    ),
                    range(2),
                )
            )
        assert any(call.get("verified") is True for call in calls) or any(
            row.get("incident", {}).get("outcome") == "success"
            for row in recovery_actions(root=root)
        )
    finally:
        launcher.send_signal(signal.SIGTERM)
        launcher.wait(timeout=60)
    assert launcher.returncode == 0, launcher.stderr.read() if launcher.stderr else ""
    assert len(set(worker_starts)) == 2

    final_budget = read_incident_budget(original_incident_id, root=root)
    assert final_budget is not None
    _assert_same_incident_budget(restarted_budget, final_budget)
    assert final_budget["charged"]["tool_attempts"] == 2

    incident_rows = [
        row
        for row in recovery_actions(root=root)
        if row.get("incident", {}).get("work_id") == task_id
        and row.get("incident", {}).get("authoritative_generation")
        == incident_generation
    ]
    assert len(incident_rows) == 1
    final_incident = incident_rows[0]["incident"]
    assert final_incident["outcome"] == "success"
    assert [
        receipt["stage"]
        for receipt in final_incident["stage_receipts"]
        if receipt["stage"] == "resolved"
    ] == ["resolved"]
    assert (
        dispatch_audit_recovery(
            root, task_id, expected_generation=incident_generation
        )
        is False
    )
    assert retry_pending_task_merges(root) == [task_id]
    assert retry_pending_task_merges(root) == []
    assert len(forge.created) == 1
    assert physical_turns == [task_id]
    refs = [line.split()[2] for line in push_log.read_text(encoding="utf-8").splitlines()]
    assert refs.count("refs/heads/feat/feat_001") == 1
    assert refs.count("refs/heads/epic/epic_001") == (1 if split_roots else 3)
    review_messages = [
        event
        for event in read_events("war_room", 0, root=root)[0]
        if event.type == "Toast"
        and event.payload.get("kind") == "feature_review_opened"
    ]
    assert len(review_messages) == 1
    # Consume the exact remainder of the original finite allowance. A later
    # expensive recovery must be refused against the same incident and retain
    # both its operation history and stable escalation identity.
    remaining_attempts = int(final_budget["remaining"]["tool_attempts"])
    assert remaining_attempts > 0
    exhaustion_operation = f"exhaust:{task_id}:{incident_generation}"
    exhaustion_claim = f"exhaustion-claim:{incident_generation}"
    assert reserve_incident_operation(
        original_incident_id,
        exhaustion_operation,
        "feature_review_reconciliation",
        {"tool_attempts": remaining_attempts},
        exhaustion_claim,
        POLICY_VERSION,
        root=root,
    ).admitted
    exhausted_settlement = settle_incident_operation(
        original_incident_id,
        exhaustion_operation,
        {
            "outcome": "success",
            "quality": "known",
            "usage": {"tool_attempts": remaining_attempts},
            "claim_complete": True,
        },
        root=root,
    )
    assert exhausted_settlement.state == "exhausted"
    exhausted_budget = read_incident_budget(original_incident_id, root=root)
    assert exhausted_budget is not None
    _assert_same_incident_budget(final_budget, exhausted_budget)
    assert exhausted_budget["status"] == "exhausted"
    assert exhausted_budget["charged"]["tool_attempts"] == 6
    assert len(exhausted_budget["operations"]) == 3
    assert exhausted_budget["wait_reason"] == "bounded_extension_required"
    escalation_id = exhausted_budget["escalation_id"]
    assert isinstance(escalation_id, str) and escalation_id
    refused_expensive_recovery = reserve_incident_operation(
        original_incident_id,
        f"refused:{task_id}:{incident_generation}",
        "feature_review_reconciliation",
        {"tool_attempts": 1},
        f"refused-claim:{incident_generation}",
        POLICY_VERSION,
        root=root,
    )
    assert refused_expensive_recovery.state == "exhausted"
    assert refused_expensive_recovery.reason == "bounded_extension_required"
    refused_budget = read_incident_budget(original_incident_id, root=root)
    assert refused_budget is not None
    assert refused_budget["incident_id"] == original_incident_id
    assert refused_budget["original_action_id"] == original_incident_id
    assert refused_budget["escalation_id"] == escalation_id
    assert refused_budget["operations"] == exhausted_budget["operations"]


@pytest.mark.parametrize(
    ("historical_state", "expected_route", "expected_url", "created"),
    [
        ("open", "refresh", "https://forge.example/pulls/original", 0),
        ("merged", "follow_up", "https://forge.example/pulls/repair", 1),
    ],
)
def test_completed_feature_repair_publishes_current_heads_and_integrates_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    historical_state: str,
    expected_route: str,
    expected_url: str,
    created: int,
) -> None:
    """A late repair keeps old acceptance separate from current delivery."""

    root, feature_entry, task_id = _completed_feature(tmp_path)
    epic_entry = get_integration_worktree(root, "epic", "epic_001")
    assert epic_entry is not None
    move_doc("feat_001", "completed", root=feature_entry.path)

    historical = MergeRequest(
        url="https://forge.example/pulls/original",
        number="1",
        forge="github",
        source_branch="feat/feat_001",
        target_branch="epic/epic_001",
        draft=False,
    )
    historical_projection = {
        "url": historical.url,
        "number": historical.number,
        "forge": historical.forge,
        "source_branch": historical.source_branch,
        "target_branch": historical.target_branch,
        "source_head": "historical-source",
        "target_head": "historical-target",
        "draft": False,
        "closed": historical_state == "merged",
        "accepted_merge_sha": (
            "historical-merge" if historical_state == "merged" else None
        ),
        "accepted_source_head": (
            "historical-source" if historical_state == "merged" else None
        ),
        "accepted_target_head": (
            "historical-target" if historical_state == "merged" else None
        ),
        "reconciliation_status": (
            "accepted" if historical_state == "merged" else "pending"
        ),
        "seen_comments": [],
        "toast_notified": True,
    }
    review._store_review_generation(
        root,
        "feat_001",
        historical_projection,
        generation=0,
        action_id=None,
    )

    admitted = admit_feature_repair(
        "feat_001",
        f"late-delivery:{task_id}",
        task_id=task_id,
        approval_reference="approved-feature-plan",
        scope_reference="late-review-reconciliation",
        root=root,
    )
    assert admitted["phase"] == "parent_enabled"
    assert admitted["generation"] == 1
    historical_row = review.feature_review_generation("feat_001", 0, root=root)
    assert historical_row is not None

    forge = DeterministicForge(historical, historical_state)
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    monkeypatch.setattr(review, "merge_request_snapshot", forge.snapshot)
    monkeypatch.setattr(review, "find_merge_request", forge.find)
    monkeypatch.setattr(review, "create_merge_request", forge.create)
    monkeypatch.setattr(review, "push_branch", lambda *_args, **_kwargs: None)

    published = review.ensure_feature_review("feat_001", root=root)
    published_record = review.review_record_for_feature("feat_001", root=root)
    assert published_record is not None
    forge.current_source_head = str(published_record["source_head"])
    replay = review.ensure_feature_review("feat_001", root=root)
    assert published is not None and replay is not None
    assert published.url == replay.url == expected_url
    assert len(forge.created) == created

    current = review.review_record_for_feature("feat_001", root=root)
    assert current is not None
    assert current["current_generation"] == 1
    assert current["action_id"] == admitted["action_id"]
    assert current["route"] == expected_route
    assert current["source_head"] == _git(feature_entry.path, "rev-parse", "HEAD")
    assert current["target_head"] == _git(epic_entry.path, "rev-parse", "HEAD")
    assert current["source_head"] != historical_row["source_head"]
    assert review.feature_review_generation("feat_001", 0, root=root) == historical_row
    if historical_state == "merged":
        assert historical_row["accepted_merge_sha"] == "historical-merge"
        assert current["previous_review_url"] == historical.url

    # Forge acceptance and Git integration are deliberately separate facts.
    # Land the exact current source on the real Epic line, then prove replay
    # cannot create another publication or authority event.
    _git(epic_entry.path, "merge", "--no-ff", "feat/feat_001", "-m", "integrate repair")
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", current["source_head"], "HEAD"],
            cwd=epic_entry.path,
            check=False,
        ).returncode
        == 0
    )
    assert review.ensure_feature_review("feat_001", root=root).url == expected_url
    authority = [
        event
        for event in read_events("feat_001", 0, root=root)[0]
        if event.type == "FeatureRepairAuthorized"
    ]
    opened = [
        event
        for event in read_events("war_room", 0, root=root)[0]
        if event.type == "Toast"
        and event.payload.get("kind") == "feature_review_opened"
    ]
    assert len(authority) == 1
    assert len(opened) == 1


def _interrupt_after_prepare(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Path, dict[str, object]], None]:
    import cascade.feature.repair as repair

    real_write = repair._write_payload
    calls = 0

    def interrupt(repo: Path, payload: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        real_write(repo, payload)
        if calls == 1:
            raise OSError("prepared repair interruption")

    monkeypatch.setattr(repair, "_write_payload", interrupt)
    return real_write


@pytest.mark.parametrize(
    "refusal",
    [
        "source_moved",
        "target_moved",
        "dirty_checkout",
        "approval_changed",
        "blocking_comment",
        "dependency_refusal",
        "live_owner",
    ],
)
def test_prepared_repair_refusals_are_typed_and_preserve_durable_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    refusal: str,
) -> None:
    """Mutable gates are reread; a refusal cannot rewrite the repair receipt."""

    root, feature_entry, task_id = _completed_feature(tmp_path)
    epic_entry = get_integration_worktree(root, "epic", "epic_001")
    assert epic_entry is not None
    move_doc("feat_001", "completed", root=feature_entry.path)
    ledger_write = _interrupt_after_prepare(monkeypatch)
    with pytest.raises(OSError, match="prepared repair interruption"):
        admit_feature_repair(
            "feat_001",
            f"late-delivery:{task_id}",
            task_id=task_id,
            approval_reference="approved-feature-plan",
            root=root,
        )

    import cascade.feature.repair as repair

    # Restore the ledger writer after the deliberately interrupted checkpoint.
    monkeypatch.setattr(repair, "_write_payload", ledger_write)

    if refusal == "source_moved":
        feature = read_doc("feat_001", root=feature_entry.path)
        feature.body += "\nLate unreviewed source edit.\n"
        write_doc(feature, root=feature_entry.path)
    elif refusal == "target_moved":
        (epic_entry.path / "target-moved.txt").write_text("moved\n", encoding="utf-8")
        _git(epic_entry.path, "add", "target-moved.txt")
        _git(epic_entry.path, "commit", "-m", "move target")
    elif refusal == "dirty_checkout":
        feature = read_doc("feat_001", root=feature_entry.path)
        feature.meta.path.write_text(
            feature.meta.path.read_text(encoding="utf-8") + "\ndirty\n",
            encoding="utf-8",
        )
    elif refusal == "approval_changed":
        feature = read_doc("feat_001", root=feature_entry.path)
        feature.meta.approved_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        write_doc(feature, root=feature_entry.path)
    elif refusal == "blocking_comment":
        comment(
            "feat_001",
            "Scope",
            "Do not admit this repair yet.",
            author="human",
            blocking=True,
            root=root,
        )
    elif refusal == "dependency_refusal":
        add_doc(
            root,
            id="feat_999",
            title="Unfinished dependency",
            tier="feature",
            parent="epic_001",
        )
        feature = read_doc("feat_001", root=feature_entry.path)
        feature.meta.depends_on = ["feat_999"]
        write_doc(feature, root=feature_entry.path)
    elif refusal == "live_owner":
        mark_running(task_id, root=root)
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(refusal)

    before_action = next(
        row
        for row in recovery_actions(root=root)
        if row.get("kind") == "feature_repair"
    )
    with pytest.raises((FeatureRepairError, GitError)):
        admit_feature_repair(
            "feat_001",
            f"late-delivery:{task_id}",
            task_id=task_id,
            approval_reference="approved-feature-plan",
            root=root,
        )
    after_action = next(
        row
        for row in recovery_actions(root=root)
        if row.get("kind") == "feature_repair"
    )
    for key in (
        "action_id",
        "generation",
        "prior_document_digest",
        "intended_document_digest",
        "source_head",
        "target_head",
    ):
        assert after_action[key] == before_action[key]
    assert after_action["phase"] == "prepared"
    assert after_action.get("authority_event_id") is None
    assert after_action.get("introduction_commit") is None
    inspected = inspect_feature_repair(
        "feat_001", f"late-delivery:{task_id}", root=root
    )
    assert inspected["phase"] == "prepared"
    assert not [
        row
        for row in recovery_actions(root=root)
        if row.get("kind") == "feature_repair"
        and row.get("phase") != "prepared"
    ]
    assert not [
        event
        for event in read_events("feat_001", 0, root=root)[0]
        if event.type == "FeatureRepairAuthorized"
    ]
