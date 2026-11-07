from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from pathlib import Path

import pytest

from cascade.resolution_actions import (
    admit_resolution_action,
    normalize_epic_031_recovery_request,
    normalize_operator_request,
    resolve_review_context,
    resolution_action,
)
from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
from tests.support import add_doc, make_repo


def _operator_payload() -> dict[str, object]:
    return {
        "review_id": "147",
        "review_url": "https://forge.example/repo/pull/147",
        "source_ref": "feat/feat_035_001",
        "target_ref": "epic/epic_035",
        "observed_source_head": "source-sha",
        "observed_target_head": "target-sha",
        "requester": "operator:alice",
        "assignee": "feature:feat_035_001",
    }


def test_operator_and_epic_031_paths_normalize_to_one_identity(tmp_path: Path) -> None:
    operator = normalize_operator_request(_operator_payload())
    recovery = normalize_epic_031_recovery_request(
        {
            "review": {
                "id": "147",
                "url": "https://forge.example/repo/pull/147",
                "source_branch": "feat/feat_035_001",
                "target_branch": "epic/epic_035",
            },
            "source_sha": "source-sha",
            "target_sha": "target-sha",
            "actor": "supervisor:epic_031",
            "assignment": {"assigned_team": "feature:feat_035_001"},
        }
    )

    assert operator.source == "operator"
    assert recovery.source == "epic_031_recovery"
    assert operator.idempotency_key == recovery.idempotency_key


def test_duplicate_admission_reuses_original_action_across_entry_paths(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    first = admit_resolution_action(normalize_operator_request(_operator_payload()), root=root)
    duplicate = admit_resolution_action(
        normalize_epic_031_recovery_request(
            {
                "review": {
                    "id": "147",
                    "url": "https://forge.example/repo/pull/147",
                    "source_branch": "feat/feat_035_001",
                    "target_branch": "epic/epic_035",
                },
                "source_sha": "source-sha",
                "target_sha": "target-sha",
                "actor": "supervisor",
                "assignment": {"owner": "epic:epic_035"},
            }
        ),
        root=root,
    )

    assert first.reused is False
    assert duplicate.reused is True
    assert duplicate.action_id == first.action_id
    assert duplicate.action["request"] == first.action["request"]
    assert resolution_action(first.action_id, root=root) == first.action


def test_concurrent_duplicate_admission_creates_one_action(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    request = normalize_operator_request(_operator_payload())

    with ThreadPoolExecutor(max_workers=4) as pool:
        admissions = list(
            pool.map(
                lambda _unused: admit_resolution_action(request, root=root),
                range(4),
            )
        )

    assert sum(not item.reused for item in admissions) == 1
    assert {item.action_id for item in admissions} == {request.idempotency_key}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("review_id", "", "review_id is required"),
        ("source_ref", "", "source_ref is required"),
        ("observed_source_head", "", "observed_source_head is required"),
        ("requester", "", "requester is required"),
        ("assignee", "", "assignee is required"),
    ],
)
def test_normalization_rejects_missing_required_metadata_without_persistence(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    root = make_repo(tmp_path)
    payload = _operator_payload()
    payload[field] = value

    with pytest.raises(ValueError, match=message):
        normalize_operator_request(payload)

    assert not (root / ".cascade" / "resolution_actions.json").exists()


def test_normalization_rejects_closed_review_and_mutation_like_ref(tmp_path: Path) -> None:
    payload = _operator_payload()
    payload["source_ref"] = "--force"
    with pytest.raises(ValueError, match="authorized ref"):
        normalize_operator_request(payload)

    payload = _operator_payload()
    payload["review_state"] = "closed"
    with pytest.raises(ValueError, match="must be open"):
        normalize_operator_request(payload)

    payload = _operator_payload()
    payload["review_url"] = "mailto:owner@example.test"
    with pytest.raises(ValueError, match="absolute HTTP"):
        normalize_operator_request(payload)


def _write_review_registry(root: Path, records: dict[str, object]) -> None:
    path = root / ".cascade" / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def _review_board(root: Path) -> None:
    add_doc(root, id="epic_035", title="Epic", tier="epic")
    add_doc(
        root,
        id="feat_035_001",
        title="Feature",
        tier="feature",
        parent="epic_035",
    )


def _admission_ready_root(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = make_repo(tmp_path)
    _review_board(root)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "seed"], cwd=root, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "branch", "feat/feat_035_001"], cwd=root, check=True)
    subprocess.run(["git", "branch", "epic/epic_035"], cwd=root, check=True)
    save_registry(
        root,
        [IntegrationWorktree("feature", "feat_035_001", "feat/feat_035_001", root, sha)],
    )
    record: dict[str, object] = {
        "url": "https://forge.example/repo/pull/147",
        "number": "147",
        "source_branch": "feat/feat_035_001",
        "target_branch": "epic/epic_035",
        "source_head": sha,
        "target_head": sha,
        "credentials_available": True,
        "resolution_permitted": True,
    }
    _write_review_registry(root, {"feat_035_001": record})
    payload = _operator_payload()
    payload["observed_source_head"] = sha
    payload["observed_target_head"] = sha
    return root, payload


def _assert_admission_commands_are_read_only(commands: list[tuple[str, ...]]) -> None:
    """Admission may inspect Git, but must not invoke a mutation-capable command."""

    assert all(
        command[:2] in {("git", "rev-parse"), ("git", "status"), ("git", "merge-base")}
        for command in commands
    )


def test_admission_persists_a_non_mutating_handoff_after_all_safety_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, payload = _admission_ready_root(tmp_path)
    commands: list[tuple[str, ...]] = []
    run = subprocess.run

    def record_command(
        command: object, *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(command, list):
            commands.append(tuple(str(part) for part in command))
        return run(command, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("cascade.resolution_actions.subprocess.run", record_command)

    admission = admit_resolution_action(normalize_operator_request(payload), root=root)

    assert admission.action["status"] == "mutation_ready"
    handoff = admission.action["handoff"]
    assert isinstance(handoff, dict)
    assert handoff["mutation_performed"] is False
    assert handoff["authorized_refs"] == ["feat/feat_035_001", "epic/epic_035"]
    assert commands
    _assert_admission_commands_are_read_only(commands)


def test_admission_accepts_clean_local_resolution_containing_both_review_heads(
    tmp_path: Path,
) -> None:
    root, payload = _admission_ready_root(tmp_path)
    subprocess.run(["git", "checkout", "epic/epic_035"], cwd=root, check=True, capture_output=True, text=True)
    (root / "target.txt").write_text("target\n", encoding="utf-8")
    subprocess.run(["git", "add", "target.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "advance target"], cwd=root, check=True, capture_output=True, text=True)
    target_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", "feat/feat_035_001"], cwd=root, check=True, capture_output=True, text=True)
    (root / "source.txt").write_text("source\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "advance source"], cwd=root, check=True, capture_output=True, text=True)
    source_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    payload.update(observed_source_head=source_sha, observed_target_head=target_sha)
    subprocess.run(["git", "merge", "epic/epic_035", "--no-edit"], cwd=root, check=True, capture_output=True, text=True)

    admission = admit_resolution_action(normalize_operator_request(payload), root=root)

    assert source_sha != target_sha
    assert admission.action["status"] == "mutation_ready"


@pytest.mark.parametrize(
    ("change", "checkpoint", "code", "resume_fragment"),
    [
        ("stale", "observed_heads", "stale_observed_heads", "Refresh review heads"),
        ("credentials", "credentials", "credentials_unavailable", "Restore the review credentials"),
        ("dirty", "worktree_clean", "dirty_unrelated_paths", "Commit, stash, or discard"),
    ],
)
def test_admission_persists_actionable_boundary_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    checkpoint: str,
    code: str,
    resume_fragment: str,
) -> None:
    root, payload = _admission_ready_root(tmp_path)
    if change == "stale":
        subprocess.run(["git", "commit", "--allow-empty", "-m", "advance"], cwd=root, check=True)
        subprocess.run(["git", "branch", "-f", "feat/feat_035_001", "HEAD"], cwd=root, check=True)
    elif change == "credentials":
        _write_review_registry(root, {"feat_035_001": {**json.loads((root / ".cascade" / "reviews.json").read_text())["feat_035_001"], "credentials_available": False}})
    else:
        (root / "unrelated.txt").write_text("dirty\n", encoding="utf-8")

    commands: list[tuple[str, ...]] = []
    run = subprocess.run

    def record_command(
        command: object, *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(command, list):
            commands.append(tuple(str(part) for part in command))
        return run(command, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("cascade.resolution_actions.subprocess.run", record_command)
    admission = admit_resolution_action(normalize_operator_request(payload), root=root)

    assert admission.action["status"] == "blocked"
    blocker = admission.action["blocker"]
    assert isinstance(blocker, dict)
    assert blocker["checkpoint"] == checkpoint
    assert blocker["code"] == code
    assert blocker["observed_refs"] == ["feat/feat_035_001", "epic/epic_035"]
    assert blocker["observed_shas"] == [payload["observed_source_head"], payload["observed_target_head"]]
    assert resume_fragment in blocker["resume_action"]
    _assert_admission_commands_are_read_only(commands)


def test_context_routes_a_feature_review_to_its_feature_team(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _review_board(root)
    _write_review_registry(
        root,
        {
            "feat_035_001": {
                "url": "https://forge.example/repo/pull/147",
                "number": "147",
                "source_branch": "feat/feat_035_001",
                "target_branch": "epic/epic_035",
                "closed": False,
            }
        },
    )

    resolution = resolve_review_context(normalize_operator_request(_operator_payload()), root=root)

    assert resolution.blocker is None
    assert resolution.context is not None
    assert resolution.context.owning_scope == "feature:feat_035_001"
    assert resolution.context.accountable_team == "feature:feat_035_001"
    assert resolution.context.authorized_refs == ("feat/feat_035_001", "epic/epic_035")
    assert resolution.context.observed_source_head == "source-sha"
    assert resolution.context.worktree is None
    assert root / ".cascade" / "reviews.json" in resolution.context.inspection_paths


def test_context_routes_an_explicitly_assigned_child_review_to_its_epic_team(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _review_board(root)
    _write_review_registry(
        root,
        {
            "feat_035_001": {
                "url": "https://forge.example/repo/pull/147",
                "number": "147",
                "source_branch": "feat/feat_035_001",
                "target_branch": "epic/epic_035",
                "closed": False,
            }
        },
    )
    payload = _operator_payload()
    payload["assignee"] = "epic:epic_035"

    resolution = resolve_review_context(normalize_operator_request(payload), root=root)

    assert resolution.blocker is None
    assert resolution.context is not None
    assert resolution.context.owning_scope == "feature:feat_035_001"
    assert resolution.context.accountable_team == "epic:epic_035"


def test_context_routes_an_epic_review_to_its_epic_team(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _review_board(root)
    _write_review_registry(
        root,
        {
            "epic_035": {
                "url": "https://forge.example/repo/pull/147",
                "number": "147",
                "source_branch": "feat/feat_035_001",
                "target_branch": "epic/epic_035",
                "closed": False,
            }
        },
    )
    payload = _operator_payload()
    payload["assignee"] = "epic:epic_035"

    resolution = resolve_review_context(normalize_operator_request(payload), root=root)

    assert resolution.blocker is None
    assert resolution.context is not None
    assert resolution.context.owning_scope == "epic:epic_035"
    assert resolution.context.accountable_team == "epic:epic_035"


def test_context_blocks_ref_and_cross_feature_assignment_ambiguity(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _review_board(root)
    add_doc(root, id="epic_036", title="Other epic", tier="epic")
    _write_review_registry(
        root,
        {
            "feat_035_001": {
                "url": "https://forge.example/repo/pull/147",
                "number": "147",
                "source_branch": "feat/feat_035_001",
                "target_branch": "epic/epic_035",
                "closed": False,
            }
        },
    )

    payload = _operator_payload()
    payload["target_ref"] = "epic/epic_036"
    refs = resolve_review_context(normalize_operator_request(payload), root=root)
    assert refs.context is None
    assert refs.blocker is not None
    assert refs.blocker.code == "unauthorized_review_refs"

    payload = _operator_payload()
    payload["assignee"] = "epic:epic_036"
    ambiguous = resolve_review_context(normalize_operator_request(payload), root=root)
    assert ambiguous.context is None
    assert ambiguous.blocker is not None
    assert ambiguous.blocker.code == "ambiguous_cross_feature_owner"
