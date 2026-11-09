# Task 013.004.005 parent recovery acceptance

## Scope and evidence

`tests/watchdog/test_parent_recovery_e2e.py` creates a disposable Git repository and uses the production Epic activation, Feature dispatch, default recovery capability registry, capability probe, locked reservation, Feature adapter, Epic adapter, completion reconciliation, and Git publication paths. No callback substitutes for recovery mutation or publication.

The flow proves:

- unchanged parent evidence across the configured 30-minute interval before either repair is admitted;
- Feature-owned Task rollup publishes the exact Feature head onto `epic/epic_001`, removes the Feature worktree, records request/acknowledgement/result, and emits one `FeatureCompleted` event;
- an Epic publication conflict stays owned and retryable with the exact durable result;
- a concurrent manual merge changes the authoritative generation, after which the registered Epic adapter publishes terminal state to `main`, removes the Epic worktree, and emits one `EpicCompleted` event;
- replay after terminal reconciliation performs no second adapter invocation, event, publication, or cleanup.

The acceptance flow exposed and fixed a real admission gap: parent no-progress episodes were process-local, while bounded admission uses a spawned process. Admission now receives the supervisor's earned episode snapshot and still rereads current authority before reserving or mutating.

## Commands and outcomes

- `pytest -q tests/watchdog/test_parent_recovery_e2e.py -x`
  - PASS: `1 passed in 19.14s` after the implementation was complete.
- `pytest -q tests/watchdog/test_parent_recovery_e2e.py tests/watchdog/test_audit_recovery.py tests/watchdog/test_audit_protected_waits.py tests/watchdog/test_audit_admission_cleanup.py tests/watchdog/test_capabilities.py tests/watchdog/test_reservations.py tests/feature/test_audit_recovery.py tests/feature/test_publication.py tests/feature/test_review_registry_races.py tests/epic/test_recovery_adapter.py tests/test_review_health.py tests/test_completion_rollup_integration.py`
  - PARTIAL: `88 passed, 3 failed in 108.72s`.
  - The three failures are all pre-existing non-Git completion-fixture failures in `tests/test_completion_rollup_integration.py`; `write_closeout` receives an empty merged board and rejects `feat_001` because `epic_001` is absent.
- `pytest -q tests/test_completion_rollup_integration.py -x`
  - FAIL independently at the first affected fixture with the same empty-board `SchemaError`, confirming it does not depend on the new acceptance test or test order.
- `pytest -q tests/watchdog/test_parent_recovery_e2e.py tests/watchdog/test_audit_recovery.py tests/watchdog/test_audit_protected_waits.py tests/watchdog/test_audit_admission_cleanup.py tests/watchdog/test_capabilities.py tests/watchdog/test_reservations.py tests/feature/test_audit_recovery.py tests/feature/test_publication.py tests/feature/test_review_registry_races.py tests/epic/test_recovery_adapter.py tests/test_review_health.py`
  - PASS: `83 passed in 107.32s`.

## Genuine limitation

The isolated acceptance repository has no authenticated forge, so terminal publication is proven by concrete Git ancestry and durable review/completion state rather than opening a hosted pull request. Existing focused Feature publication and review-health suites remain in the validation command. The independently reproducible non-Git completion-fixture failures above remain outside this task's parent-admission change.

Final supervised validation is recorded by the Task lifecycle after the deliverable commit.
