# Epic 013 integrated audit release evidence

## Release revision and selected command

The integrated product revision is
`ae3180f513015b9001420700f23ce29ca0fe7fe4`. Cascade's supervised runner
executed the following command on that clean revision without installing or
upgrading any dependency:

```text
pytest -q tests/watchdog/test_config.py tests/watchdog/test_audit.py tests/watchdog/test_audit_candidates.py tests/watchdog/test_audit_lane.py tests/watchdog/test_audit_recovery.py tests/watchdog/test_audit_protected_waits.py tests/watchdog/test_capabilities.py tests/watchdog/test_incidents.py tests/watchdog/test_reservations.py tests/watchdog/test_recovery_lock_scope.py tests/watchdog/test_parent_recovery_e2e.py tests/test_task_recovery_generations_regressions.py tests/feature/test_audit_recovery.py tests/war_room/test_health_audit_routes.py tests/war_room/test_audit_status_ui.py tests/workspace/test_init.py tests/workspace/test_worker_startup_recovery.py
```

Observed result: `188 passed in 227.81s`; exit code 0. The supervised result
included `final_validation` for Task `task_013_005_005` and deliverable SHA
`ae3180f513015b9001420700f23ce29ca0fe7fe4`.

## Success-criterion map

Every row below uses the exact command and integrated revision above.

| Epic criterion | Selected integrated evidence | Observed result |
| --- | --- | --- |
| 1 | `test_health_audit_config_defaults_independently_of_automation`, `test_omitted_health_audit_table_keeps_default_on_configuration`, and `test_init_creates_board_columns_gitignore_and_toml` prove omitted configuration is enabled at 1,800 seconds for existing and new workspaces; strict interval/bounds cases cover explicit settings. | PASS in the 188-test result. |
| 2 | Audit-lane restart, cross-process claim, receipt adoption, manual/periodic coalescing, and disabled-manual tests cover monotonic scheduling, one workspace claim, restart recovery, and no catch-up duplication. | PASS. |
| 3 | Candidate and observation suites scan all tiers, bounded recent completion inventory, unresolved old references, and canonical split repositories. | PASS. |
| 4 | Task audit, reservation, generation regression, and recovery-entry tests cover leases/checkpoints, pinned delivery, queues/actions, validation, dirty work, dependencies, merge and rollup. | PASS. |
| 5 | `test_registered_feature_and_epic_recovery_publish_and_finish_once`, protected-wait cases, and Feature adapter/publication tests cover owner, graph, approval/comment, integration/publication and rollup state. | PASS. |
| 6 | The same terminal parent fixture covers Epic owner, dispatch/publication/closeout, sign-off gates, integration state and exactly-once completion. | PASS. |
| 7 | `test_healthy_candidate_and_observation_are_byte_silent`, disabled-lane silence, and worker startup cases prove no healthy lifecycle, event, chat, model, Git or timestamp write beyond the documented receipt. | PASS. |
| 8 | Typed identity, locked recheck, changed/disappeared/gated reservation, and concurrent-claim cases prove stable identity plus a fresh lock-bound recheck before mutation. | PASS. |
| 9 | Capability registry/probe and real Task/Feature/Epic entry fixtures execute the existing scoped owner adapters. | PASS. |
| 10 | Protected comment, approval, human-action, dependency and dirty-worktree cases fail closed and retain exact resume evidence. | PASS. |
| 11 | Healthy/pure projections perform no model turn; deterministic recovery cases defer owner/model kickoff and bind only the selected capability. | PASS. |
| 12 | Incident eligibility, finite attempts, crash-before/after-handoff, restart reclaim, late result rejection and terminal replay prove bounded idempotent convergence. | PASS. |
| 13 | Capability owner checks and terminal Task-to-Feature, Feature-to-Epic recovery fixtures verify accountable hierarchical routing. | PASS. |
| 14 | War Room route/UI tests cover receipt fields, tier/outcome counts, truthful current incidents, missing/malformed evidence, guarded run-now, coalescing, and unchanged periodic deadline. `GET /api/health` remains readiness; detail is at `GET /api/health/audit`. | PASS. |
| 15 | Work/pass budgets, fair cursors, candidate/observer timeouts, nonregular stores, helper reaping and lock-scope tests prove bounded work and unrelated-delivery isolation. | PASS. |
| 16 | `test_audit_requeues_lost_validated_delivery_through_original_action` repeats the `task_038_002_002` lost-queue regression through the audit entry and reaches the original terminal action once. | PASS. |
| 17 | The selected suite covers stale/live owners, missing/stale evidence, dirty worktrees, conflicts/busy claims, approval/comments, split repositories, concurrency, disabled/invalid intervals, restart and healthy silence. | PASS. |
| 18 | `test_audit_lane_starts_before_blocking_worktree_repair`, bounded FIFO/Git descendant tests, and operator cancellation prove the independent lane progresses while ordinary watchdog I/O is blocked. | PASS. |
| 19 | Registry startup, concrete owner/action/worktree reachability, durable probe and missing-capability tests prove executable authority rather than labels. | PASS. |
| 20 | Incident generation, cooldown, capability-arrival, changed authority, retry bounds and exact-token claim tests cover all non-success re-evaluation semantics. | PASS. |
| 21 | Parent no-progress interval, live-owner silence, child dispatch and terminal Feature/Epic recovery cases detect and repair owner/publication/closeout stalls. | PASS. |
| 22 | `test_audit_requeues_lost_validated_delivery_through_original_action` and `test_registered_feature_and_epic_recovery_publish_and_finish_once` perform real isolated Git/lifecycle mutations through terminal Task, Feature and Epic outcomes exactly once. | PASS. |
| 23 | Typed identity rejection and `test_parent_revision_cannot_substitute_for_typed_feature_identity` repeat the Feature-ID-versus-`parent_rev` regression. | PASS. |
| 24 | Default capability registry, probe/reprobe, original action identity, and all-tier terminal fixtures exercise the delivered stale-delivery and child-ownership adapters without duplicating their algorithms. | PASS. |

## Default-on release decision

The temporary `health_audit_periodic_opted_in` runtime seam was removed only
after the real Task and parent terminal fixtures passed. `read_health_audit_config`
now directly controls worker activation: omitted configuration starts scheduled
audits enabled every 30 minutes regardless of `automation.enabled` and legacy
maintenance settings. Explicit `enabled = false` suppresses scheduling while
the authenticated manual route remains available and does not move the periodic
deadline.

The War Room projection also rechecks each non-success ledger row against the
fresh authoritative generation within a shared two-second/100-row bound. A
resolved or superseded historical row remains durable but is not presented as
active. Missing and malformed receipts are separately reported as unavailable
and never converted into invented healthy counts.
