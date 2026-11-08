from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cascade.task.action_recovery import (
    create_or_load_action,
    finalize_attempt,
    load_action,
    record_action_checkpoint,
    start_attempt,
    update_recovery_record,
)
from cascade.watchdog.incidents import (
    authoritative_generation,
    incident_record,
    project_incident,
)
from tests.support import make_repo


def _generation(**evidence: object) -> str:
    return authoritative_generation(
        work_id="task_001",
        tier="task",
        evidence=evidence,
        capability="retry_task",
    )


def test_only_success_for_unchanged_generation_suppresses_permanently() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    generation = _generation(lease="expired", branch_head="a", queued=False)
    success = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature:feat_001",
        failure_class="stale",
        generation=generation,
        evidence={"lease": "expired", "branch_head": "a", "queued": False},
        selected_capability="retry_task",
        outcome="success",
        now=now,
    )

    assert (
        project_incident(generation, {"old": {"incident": success}}, now=now).state
        == "suppressed"
    )
    changed = _generation(lease="expired", branch_head="b", queued=False)
    assert project_incident(changed, {"old": {"incident": success}}, now=now).eligible


def test_claims_and_failures_have_finite_reassessment() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    generation = _generation(checkpoint="one")
    for outcome, seconds in (
        ("claimed", 300),
        ("error", 60),
        ("refused", 60),
        ("deferred", 60),
        ("unsafe", 60),
        ("no_op", 60),
    ):
        row = incident_record(
            work_id="task_001",
            tier="task",
            accountable_owner="feature:feat_001",
            failure_class="stale",
            generation=generation,
            evidence={"checkpoint": "one"},
            selected_capability="retry_task",
            outcome=outcome,  # type: ignore[arg-type]
            now=now,
        )
        ledger = {"row": {"incident": row}}
        assert project_incident(generation, ledger, now=now).state == "cooldown"
        assert project_incident(
            generation, ledger, now=now + timedelta(seconds=seconds + 1)
        ).eligible


def test_failure_classes_have_independent_retry_eligibility() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    generation = _generation(checkpoint="one")
    success = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature:feat_001",
        failure_class="stale_execution",
        generation=generation,
        evidence={"checkpoint": "one"},
        selected_capability="retry_task",
        outcome="success",
        now=now,
    )
    ledger = {"old": {"incident": success}}
    assert not project_incident(
        generation, ledger, failure_class="stale_execution", now=now
    ).eligible
    assert project_incident(
        generation, ledger, failure_class="missing_checkpoint", now=now
    ).eligible
    observation = SimpleNamespace(
        generation=generation,
        incident=SimpleNamespace(failure_class="missing_checkpoint"),
    )
    assert project_incident(observation, ledger, now=now).eligible


def test_success_remains_terminal_if_later_row_has_same_identity() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    generation = _generation(checkpoint="one")
    common = dict(
        work_id="task_001",
        tier="task",
        accountable_owner="feature:feat_001",
        failure_class="stale_execution",
        generation=generation,
        evidence={"checkpoint": "one"},
        selected_capability="retry_task",
    )
    ledger = {
        "success": {"incident": incident_record(**common, outcome="success", now=now)},
        "later": {
            "incident": incident_record(
                **common, outcome="claimed", now=now + timedelta(minutes=1)
            )
        },
    }
    assert project_incident(
        generation, ledger, failure_class="stale_execution", now=now
    ).state == "suppressed"


def test_legacy_rows_are_readable_and_action_generations_keep_history(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    action = create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=2,
        metadata={"task_id": "task_001", "queued": False},
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
    )
    first_generation = action["incident"]["authoritative_generation"]
    record_action_checkpoint(
        "task_001:delivery",
        "checkpoint-1",
        root=root,
        refs={"source": "task/task_001", "target": "feat/feat_001"},
        shas={"source_head": "a", "target_head": "b"},
        resume_instructions="resume safely",
    )
    changed = load_action("task_001:delivery", root=root)
    assert changed is not None
    assert changed["incident"]["authoritative_generation"] != first_generation
    assert (
        changed["incident_history"][0]["authoritative_generation"] == first_generation
    )

    start_attempt("task_001:delivery", root=root)
    finalized = finalize_attempt(
        "task_001:delivery",
        1,
        root=root,
        outcome="failed",
        classification="transient_retry",
        recovery_state="retryable",
    )
    assert finalized["incident"]["attempts"][0]["outcome"] == "failed"
    assert project_incident(
        _generation(old=True), {"legacy": {"result": "error"}}
    ).eligible


def test_action_incident_generation_tracks_capability_authority(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)

    class Registry:
        def __init__(self, fingerprint: str) -> None:
            self.value = fingerprint

        def fingerprint(self) -> str:
            return self.value

    monkeypatch.setattr(
        "cascade.watchdog.capabilities.default_capability_registry",
        lambda: Registry("authority-v1"),
    )
    action = create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=2,
        lifecycle_state="queued",
        metadata={"task_id": "task_001"},
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
    )
    first_generation = action["incident"]["authoritative_generation"]

    monkeypatch.setattr(
        "cascade.watchdog.capabilities.default_capability_registry",
        lambda: Registry("authority-v2"),
    )
    changed = update_recovery_record(
        "task_001:delivery", root=root, lifecycle_state="queued"
    )

    assert changed["incident"]["authoritative_generation"] != first_generation
    assert changed["incident_history"][-1]["authoritative_generation"] == first_generation
