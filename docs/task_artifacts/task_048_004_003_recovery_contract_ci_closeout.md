# Recovery contract CI and architecture closeout

## Delivered gate and local reproduction

The automatic `Recovery contract` workflow runs for pull requests and pushes to
`main`. Its 10-minute job bound contains an 8-minute pytest bound so a timeout is
a failed check while still leaving time to redact and retain a maximum 64 KiB
diagnostic tail for seven days. The artifact excludes the checkout path, terminal
escapes, control characters, and common credential-shaped values; the raw log is
removed on every outcome.

The exact command documented in `README.md` and encoded in the workflow retains
the prior review health, rebase, resolution-action and
publication safeguards, Task 1's colocated/split-root owner journey, the
post-push/pre-receipt and original-budget regressions, and Task 2's budget,
provider, reservation, investigation, independent-postcheck and receipt tests.
The five mutation-sensitive cases remain mapped to the retained evidence in
`docs/task_artifacts/task_048_004_002_adversarial_recovery_closeout.md`; no
mutation or weakened production gate is checked in.

The original
`test_validation_and_publication_failures_remain_owned_and_retryable` safeguard
is retained unchanged in `tests/test_review_health.py`, and that complete file is
part of the mandatory selection. The accepted correction
`51cffe146b8b423027266f8469678c482e321c79` and its F4 integration
`111319e52bd202fdabca20bdb315fa3a5f9f2627` are ancestors of the final Task
tree. The integration preserves provider-parent receipt attributes, review
material fingerprints, cumulative numerical exhaustion, and independent finite
extension without resetting the incident or its history. The focused regression
selection covering the original safeguard, changed/A–B–A material, cumulative
allowance, and linked provider validator passed four tests in 7.41 seconds.

## Architecture and design reconciliation

Reviewed `DESIGN.md`, `cascade/DESIGN.md`, and
`cascade/{task,agent,watchdog,workspace,feature,epic,war_room}/DESIGN.md` against
the integrated source and the repository-owned `model.dsl`, `views.dsl`, and
`workspace.contract.json`. The final tree changes CI wiring and the local runbook,
and integrates the review-material retry behavior in `action_recovery.py`,
`incident_budget.py`, and `team_review_recovery.py`. `cascade/DESIGN.md` records
the cross-component publication rule; `cascade/task/DESIGN.md` now records the
Task-owned fingerprint, restart, changed-material and remaining-allowance rules.
No public signature, durable schema version, deployed boundary, library/provider
wiring, authority owner or process-isolation boundary changed.

| Level / views inspected | Reconciliation result |
|---|---|
| `cascade-landscape`, `cascade-context` | No person, provider, forge, renderer or Cascade responsibility changed. The harness remains repository-local verification. |
| `cascade-containers` | No deployed process, communication path, repository store or persistence boundary was added. CI creates only ephemeral test fixtures and bounded diagnostics. |
| `cascade-supervisor-components`, `cascade-team-components`, `cascade-cli-components`, `cascade-war-room-components` | No component responsibility, route or collaboration changed. The gate exercises the existing supervisor/team/publication/postcheck relationships. |
| `cascade-task-code` | For a `review_validator` whose original action is `review_rebase`, `reserve_incident_operation` admits changed review material only against remaining original allowance and refuses unchanged/legacy-unverified material; `settle_incident_operation` retains its deterministic `material_fingerprint` without exhausting unrelated remaining allowance. Durable receipt `attributes`, including a linked provider's `parent_operation_id`, coexist with that fingerprint. Non-`review_rebase` linked validators retain parent/claim checks and conservative incident-wide deterministic exhaustion. Function kinds, paths, owner and Code-view relationships remain correct. |
| `cascade-agent-code` | Provider admission/settlement symbols, metering state and physical-dispatch wiring are unchanged. |
| `cascade-watchdog-code` | Reservation, investigation deduplication and `reconcile_parent_lifecycle_incident` ownership and kinds are unchanged. |
| `cascade-teams-code` | `publish_team_review_resolution` adds the immutable source tree to validation material. Validation/publication symbols, Function kinds, component owner and relationships remain correct. |
| `cascade-epic-code`, `cascade-feature-code`, `cascade-workspace-code`, `cascade-workspace-commands-code`, `cascade-dashboard-code`, `cascade-war-room-http-code` | No symbol, declaration kind, owner, HTTP/CLI route, loaded-state contract or renderer behavior changed. |

The normal trace remains original incident admission → scoped owner execution →
immutable validation → leased publication → remote/loaded observation → fresh
Watchdog postcheck. On deterministic failure of a `review_rebase` validator,
settlement fences the exact material. Restart, cosmetic commits and an A–B–A
cycle retain that refusal; genuinely changed material can reserve only the
original remaining allowance, and numerical exhaustion requires independent
finite extension with history intact. A legacy unverified receipt fails closed
after restart. A validator linked to a non-`review_rebase` provider parent keeps
its durable parent/claim attributes but conservatively exhausts the incident on
deterministic failure. Worktrees and local process groups are correctness
boundaries, not OS, network or credential isolation.

## Verification and limitations

- The initial recovery selection passed 162 tests with two existing Python
  multi-threaded `fork()` deprecation warnings in 199.38 seconds only while the
  retry safeguard carried a weakened expectation. Restoring the safeguard exposes
  the production retry-regression described above; the final supervised result
  is expected to fail at
  `test_validation_and_publication_failures_remain_owned_and_retryable`. The
  focused check on safeguard-restoration commit
  `acad4d9cd0ec9701676f9fec69204c9c86169592` failed at that assertion in 1.74
  seconds: expected `completed`, observed `awaiting_owner_decision`. The final
  supervised pre-correction selection ran on deliverable
  `10b9dd739383befe7dae96585002bb82aa82b406` and returned 161 passed and one
  failed in 203.12 seconds with `final_validation`. The sole failure was the same
  mandatory assertion: expected `completed`, observed
  `awaiting_owner_decision`. This is retained failure evidence, not final
  acceptance.
- After supported integration, the four focused material/provider regressions
  passed in 7.41 seconds. The complete supervised selection then passed 163 tests
  with two existing multi-threaded `fork()` deprecation warnings in 231.25
  seconds on clean deliverable `cf3ea5594d6d8381ce80441067bfc04427000723`;
  the final post-closeout validation is retained by the Task delivery receipt.
- Final source/navigation behavior: 18 passed in 4.82 seconds. This covered
  the source contract and real symbols/kinds/owners, context → container →
  component → Code behavior, Level up, deep-link and pinned-source UI cases,
  immutable offline/bounded renderer command construction, scheduler
  deduplication and warm artifact reuse across restart.
- `git diff --check` and workflow YAML parsing passed.
- The exact pinned Structurizr image was present in the shared Docker cache as
  `sha256:97681b22557abb2044ff2b67ae374956824c01da46b76be60858281adf678864`
  (`linux/amd64`); no pull or installation occurred. On the final integrated tree,
  the unmodified real renderer and Chromium journey passed three tests in 190.48
  seconds (196.77 seconds wall, 175,260 KiB maximum RSS). It exercised
  context → container → component → Code, Level up, deep-link restoration,
  pinned-source opening, warm artifact reuse, renderer failure states and bounded
  scheduling against the byte-unchanged revision-pinned architecture source.
- No live deployment, provider credentials or controlled supervisor incident was
  used. That independently authorized operational evidence remains Task 4 scope.

The prior pre-correction red results remain retained evidence. Final deterministic
acceptance uses the complete bounded selection on the clean committed Task tree;
the supervised delivery receipt is the authoritative result. Controlled live
supervisor authority and deployment evidence remain separate Task 4 obligations.
