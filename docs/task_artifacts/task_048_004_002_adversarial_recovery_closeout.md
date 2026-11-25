# Adversarial recovery and cumulative-budget closeout

## Scope and revision

The deterministic evidence was exercised from checkout
`c87a2a00d8d6b50bddf33fa6e91a8c41355599f5` with the Task test changes applied.
The pinned Feature baseline is `61f74c66d0054db91b6bc6177c1a49b7b096a07c`;
the integrated source includes the declared F1/F2/F3 ancestors and Task 1 test
change `bc008c8788053418098f13327c92c6066ae68c0b`.

No production source, persistent schema, runtime boundary, provider wiring, or
architecture source changed. The delivered diff adds adversarial assertions to
the existing Task-budget and provider-adapter tests. The shared real-repository
journey continues to count provider turns, Task validations, worker PIDs, forge
creates, queue messages, remote ref updates, budget receipts, and terminal
postcheck receipts independently.

## Acceptance matrix

| Contract | Inspectable evidence |
|---|---|
| Real red check and immutable validation identity | `test_watchdog_owner_repair_delivers_and_independently_verifies_once` records red then green Task validation against distinct deliverable SHAs and publishes only the green SHA. |
| Malformed/infeasible policy, unchanged expensive failure, policy cycle, generation change, bounded extension | `test_corrupt_policy_and_in_flight_overrun_fail_closed_without_minting` and `test_deterministic_failure_generation_and_policy_cycles_preserve_history` compare typed state/reason, original incident, claim, operation, policy version, charged usage, and unchanged receipt history. |
| Transient cap/backoff, concurrent atomic reservation, unknown usage and cancellation | `tests/task/test_incident_budget.py` covers persisted three-attempt backoff, two-process reservation, legacy unavailable usage, and conservative interrupted charges; `tests/agent/test_provider_recovery_contract.py` covers a cancelled physical provider invocation and a waiting competitor. |
| Provider switch, cosmetic route/model change, replacement action | Provider recovery contract tests show one physical dispatch and `ProviderBudgetRefusedError(operation_identity_replayed)` without another ledger operation. |
| Absent provider capability and denied credential | `test_provider_preflight_refusal_preserves_incident_without_transport_or_charge` proves typed provider errors occur before transport, while the original incident/policy remains and paid/model counters remain zero. |
| Stale/gated admission, wrong scope, live owner, dirty checkout, changed approval/source/target, unavailable evidence | Watchdog reservation, Feature recovery, review recovery journey, publication safeguard, and late-convergence focused tests retain the durable obligation and refuse before an unpermitted effect. |
| Competing remote and policy/source drift during checks | `tests/test_review_rebase.py` and `tests/test_review_recovery_journey.py` re-read remote heads and policy after checks; typed blockers leave the admitted remote unchanged. |
| Failed or unverifiable owner result cannot resolve | Watchdog reservation receipts end in `independent_postcheck_required`; parent lifecycle postcheck returns a named pending fact until review, runtime, lease, and worktree facts all match. |
| Known, estimated, unavailable usage | Exact validator usage remains known, the overrun scenario remains estimated, and cancellation/legacy usage remains unavailable with conservative reservation charge. None is normalized to zero. |

The finite default remains six tool attempts, six paid turns, 1,800 process
seconds, 1,800 model seconds, 3,600 elapsed seconds, and 200,000 known tokens.
The real journey consumes and refuses against that original allowance rather
than creating a journey-specific policy.

The positive journey measures effects independently in both colocated and split
root layouts: one physical provider turn, two Task validator starts (one red and
one green against different deliverable SHAs), two distinct worker PIDs across
the forced restart, one forge review creation, one review-opened message, one
Feature remote-ref update, the root-specific expected Epic ref updates, and one
terminal `resolved` receipt. Its incident ledger contains two charged operations
and two tool attempts before final verification. The test then consumes the four
remaining attempts under the same policy, observes exactly six charged attempts
and three operations, and proves a later expensive reservation is refused with
`bounded_extension_required` while retaining the same escalation and operation
history. Paid-turn, model-runtime, process-runtime, elapsed-time, and token caps
are exercised independently by the provider and incident-budget selections;
they are not inferred from the physical-effect counters.

## Dependency handoff and remaining Feature obligations

Task 1's merged journey is used as executable evidence, not as proof that the
whole Feature matrix is complete. Its primary acceptance/test-plan and closeout
fields remain incomplete historical work-record evidence, and this Task does not
retroactively manufacture those records. Task 3 still owns the automatic bounded
`Recovery contract` PR/main job, fresh-workspace instructions, sanitized failure
artifacts, and final integrated architecture source/render/navigation/pinned-
source/performance and stale-symbol checks. Task 4 still owns the separately
authorized controlled supervisor run, exact deployed identity, credentials,
fault/rollback scope, installation and runtime receipts, and independent remote
and loaded-state observations. Without that authority it must retain the named
prerequisite and leave operational acceptance open. This deterministic Task ran
no live deployment and does not close either obligation.

## Controlled mutation evidence

Each mutation was applied alone with `apply_patch`, the named test was run, and
the exact patch was reversed before the clean rerun. Worktree status after all
five contained only the intended test changes and this artifact.

| Safeguard temporarily broken | Focused command | Required red assertion | Restoration |
|---|---|---|---|
| Investigation deduplication: disable the matching evidence/owner branch in `cascade/watchdog/audit_investigation.py` | `/opt/conda/bin/python3.12 -m pytest -q tests/watchdog/test_audit_investigation.py::test_material_evidence_and_cooldown_control_repeated_delivery --tb=short` | `assert request(root)["deduplicated"]` was false. | Reversed; `1 passed`. |
| Validation: ignore nonzero validator exit in `cascade/review_rebase.py` | `/opt/conda/bin/python3.12 -m pytest -q tests/test_review_rebase.py::test_failed_checks_preserve_rebased_work_and_skip_publication --tb=short` | `publication.published is False` failed because publication was true with return code 1. | Reversed; `1 passed`. |
| Immutable tested-SHA publication: suppress both HEAD equality fences and push moving `HEAD` | `/opt/conda/bin/python3.12 -m pytest -q 'tests/test_review_recovery_journey.py::test_checks_cannot_publish_a_different_head_or_policy[source]' --tb=short` | Expected `blocked`, observed `published`. | Reversed; `1 passed`. |
| Independent postcheck: mark a failed fact set verified in `cascade/watchdog/incident_postcheck.py` | `/opt/conda/bin/python3.12 -m pytest -q 'tests/watchdog/test_parent_lifecycle_postcheck.py::test_postcheck_fails_closed_when_a_relevant_fact_changes[runtime-pending:loaded_runtime_current]' --tb=short` | `result["verified"]` was true for a changed runtime. | Reversed; `1 passed`. |
| Receipt recovery: ignore the already-created remote review in `cascade/review.py` | `/opt/conda/bin/python3.12 -m pytest -q 'tests/test_late_repair_convergence.py::test_watchdog_owner_repair_delivers_and_independently_verifies_once[colocated]' --tb=short` | Unavailable forge evidence no longer raised `GitError`; the original obligation could be bypassed. | Reversed; `1 passed` in 36.73 seconds. |

An older narrow fixture,
`test_follow_up_save_failure_recovers_same_remote_review`, reports historical
forge snapshot fields on its restored path and therefore is not used as clean
mutation evidence. The active real-repository receipt journey above is the
gating proof; the older fixture mismatch is a non-production test-maintenance
gap for its owner.

## Architecture and design review

Reviewed root, package, Task, Agent, Watchdog, Workspace, and War Room designs
against the test-only diff and the pinned `model.dsl`, `views.dsl`, and
`workspace.contract.json` source contract.

| Views | Result |
|---|---|
| `cascade-landscape`, `cascade-context`, `cascade-containers` | No person, external dependency, runtime/data boundary, persistence mechanism, or communication path changed. |
| `cascade-supervisor-components`, `cascade-team-components`, `cascade-cli-components`, `cascade-war-room-components` | No component responsibility, public interface, CLI route, or HTTP route changed. Tests exercise the existing supervisor/team boundaries. |
| `cascade-task-code` | Existing `bind_incident_budget`, `reserve_incident_operation`, `settle_incident_operation`, `read_incident_budget`, and `extend_incident_budget` symbols and declaration kinds remain the implementation under test. |
| `cascade-agent-code` | Existing `admit_provider_turn`, `settle_provider_turn`, and `run_role` wiring remains unchanged; added tests prove its pre-transport refusal counters. |
| `cascade-watchdog-code` | Existing reservation, audit investigation, and `reconcile_parent_lifecycle_incident` symbols remain unchanged; mutation runs prove their deduplication and independent verification sensitivity. |
| `cascade-teams-code` | Existing immutable validation/publication and review receipt recovery symbols remain unchanged; mutation runs prove red checks, SHA drift, and missing receipts are detected. |
| Epic, Feature, Workspace, Dashboard, War Room HTTP Code views | No source symbol, declaration kind, owner, library, route, loaded-state contract, or renderer behavior changed. No model/design edit is justified by test-only coverage. |

The normal trace remains admission → owner execution → immutable validation →
lease publication → remote/runtime observation → independent postcheck. The
failure trace retains the original incident and operation ledger at the first
typed refusal or named wait. Source-contract, navigation, rendering, pinned
source, and focused recovery commands are recorded below after execution.

## Verification

- Recovery selection:
  `/opt/conda/bin/python3.12 -m pytest -q tests/test_late_repair_convergence.py tests/task/test_incident_budget.py tests/agent/test_provider_recovery_contract.py tests/test_review_publication_safeguards.py tests/test_review_recovery_journey.py tests/test_review_rebase.py tests/watchdog/test_reservations.py tests/watchdog/test_audit_investigation.py tests/watchdog/test_parent_lifecycle_postcheck.py tests/feature/test_publication.py::test_review_recovers_remote_creation_before_local_registry_write --tb=short`
  — 132 passed in 196.77 seconds. The two warnings are Python's existing
  multi-threaded `fork()` deprecation warning from the intentional two-process
  atomic-reservation test.
- Architecture/source/navigation selection:
  `/opt/conda/bin/python3.12 -m pytest -q tests/workspace/test_c4_source.py tests/workspace/test_c4_review.py::test_code_view_scope_and_source_metadata_are_semantic tests/war_room/test_architecture_tab_ui.py tests/war_room/test_design_tree_browser.py --tb=short`
  — 18 passed in 6.05 seconds.
- Every mutation command and its clean restoration result is recorded in the
  mutation table above.
- `git diff --check` passed after restoration.

Final supervised validation is recorded by the Task delivery receipt after the
deliverable commit. No live deployment, credential use, dependency installation,
or accepted architecture snapshot rewrite was performed.
