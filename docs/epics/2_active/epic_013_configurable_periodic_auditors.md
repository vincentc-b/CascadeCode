---
id: epic_013
title: Configurable periodic health audits and recovery
tier: epic
status: active
parent: null
children:
- feat_013_001
- feat_013_002
- feat_013_003
- feat_013_004
- feat_013_005
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Configurable periodic health audits and recovery

## Intent
Run a periodic, configurable health audit across Cascade Tasks, Features, and Epics. The auditor evaluates authoritative lifecycle, execution, Git/worktree, dependency, approval, queue, review, and recovery state. Healthy work produces no mutation, event, chat turn, or notification. Unhealthy work is repaired through the same guarded lifecycle capabilities used by its owning team. The auditor agent receives the least privilege necessary to resolve proven incidents, preserves active work and human approval boundaries, and escalates only when safe automated recovery cannot be established.

### Success criteria
1. Add a documented `[automation.health_audit]` section to `cascade.toml`. Auditing is enabled by default with `interval = "30m"`; operators can change the interval or disable it explicitly. Parse duration values strictly, enforce safe minimum/maximum bounds, and preserve backward compatibility for existing configuration.
2. Run at most one audit per workspace at a time. Use monotonic scheduling, bounded jitter, restart-safe last-run state, and coalescing so restarts or slow audits do not create a catch-up storm.
3. Inspect every nonterminal Task, Feature, and Epic through canonical board and lifecycle projections. Also inspect recently completed work when reconciliation, pending review, publication, or cleanup state can still be incomplete.
4. Task health covers owner lease/heartbeat, execution phase, checkpoint, pinned inputs, branch/worktree state, dirty changes, test/validation evidence, dependency readiness, pending merge index, durable merge action, retry state, parent blockage, and completed-document rollup.
5. Feature health covers planning-team liveness, task graph consistency, dependency and approval state, task integration, review publication/merge state, stale parent revisions, blocked comments, completion rollup, and dispatchable work that is making no progress.
6. Epic health covers planning-team liveness, authoritative dependencies, sign-offs and plan approval, feature graph/sequence, integration branch/worktree, review/closeout state, return/cancellation transitions, and discrepancies between trunk pointers and integration copies.
7. A healthy audit is silent and write-free: no model turn, queue event, toast, chat message, timestamp rewrite, Git commit, or external API call solely to say that health is good. Metrics may be updated only through an explicitly documented low-cost observability path that cannot trigger work.
8. Derive stable, deduplicated incident identities from work ID, observed generation/revision, and failure class. Recheck under the appropriate lifecycle lock immediately before repair; if the incident disappeared, perform no mutation.
9. Grant the auditor a named, scoped recovery role with the capabilities needed for proven repairs. It may requeue a validated delivery missing from the pending index, reclaim a stale execution lease, resume an orphaned turn from pinned state, retry transient durable actions, reconcile lifecycle documents, restore safe dispatch, complete idempotent rollups, and invoke existing team-owned conflict recovery.
10. Auditor authority never bypasses human plan/feature approval, comment gates, credentials, license acceptance, provider changes, destructive Git decisions, system dependency installation, or ambiguous semantic conflict resolution. Those cases become durable human/team incidents with exact evidence and a resume action.
11. Prefer deterministic code-level checks and repairs. Start an auditor agent only when an unhealthy incident requires bounded diagnosis or an authorized recovery plan. Supply the incident evidence and only the tools/paths relevant to that work item; do not grant arbitrary repository mutation.
12. Repairs are idempotent, attempt-bounded, and crash/restart safe. Persist attempt history, classification, owning team, evidence, next retry/cooldown, and final outcome. Repeated audits converge without duplicating merges, dispatches, reviews, agent turns, or notifications.
13. Use hierarchical escalation: a Task incident first routes to its Feature Team, a Feature incident to its Epic Team, and an Epic/system incident to the human or Boss as appropriate. The auditor may perform a safe repair directly but records which owning team would otherwise be accountable.
14. Expose last audit time, next due time, duration, counts by tier/outcome, and active incidents in the War Room. Provide a guarded human “Run health audit now” action without changing the configured schedule.
15. Prevent audit self-harm: cap work per pass, avoid holding global locks during providers/network/Git operations, respect canonical lock ordering, and surface an auditor failure without blocking unrelated delivery.
16. Regression-test the `task_038_002_002` failure: a validated Task whose merge action is `retryable` but whose ID vanished from `pending-task-merges.json` must be detected, requeued through the canonical merge path, merged exactly once, rolled up to completed, and release dependent work.
17. Cover stale-but-live owners, missing checkpoints, dirty worktrees, merge conflicts, busy targets, stale validation evidence, approval/comment gates, orphaned Feature/Epic planning turns, split-repository state, concurrent manual recovery, disabled audits, invalid intervals, restart timing, and an entirely healthy workspace.
18. Schedule health audits independently from the ordinary watchdog maintenance chain. A slow forge fetch, review poll, Git operation, or model turn cannot indefinitely delay the next audit. Bound every subprocess and network operation with explicit timeout, cancellation, and durable retry evidence.
19. Treat recovery capability as executable authority, not a label. At startup and per incident, prove the selected operation is registered, authorized for the concrete owning work ID, can reach the required worktree/action, and has a durable request/acknowledgement/result path. Missing capability is an actionable system incident, not investigating.
20. Make remediation and recovery ledgers generation-aware. claimed, error, refused, deferred, unsafe, and prior no-op rows receive bounded retry/cooldown semantics and are re-evaluated when leases, branch heads, queue membership, evidence, document revision, parent blockage, or capability availability changes. Only terminal success for the same authoritative generation is permanently suppressing.
21. Detect active Features and Epics with no live planning owner, no pending queue input, no open/pending review, dispatchable children making no progress, or completed local integration work not published for review. Provide concrete Feature-parent and Epic-parent recovery actions rather than classifying them healthy_or_not_actionable.
22. Validate repair adapters with real end-to-end mutations in isolated repositories: route to the concrete owner, wake it, acknowledge, modify only the owned branch, run work-defined supervised checks, publish replacement evidence, clear only matching derived blockers, resume the original action, and reach terminal completion exactly once. Event-only and mocked-callback tests do not satisfy recovery acceptance.
23. Verify recovery identity fields by type and authority. Work IDs, document revisions, commit SHAs, branch names, and incident generations are not interchangeable; specifically cover the orphan-resume regression where a Task parent revision was passed as its Feature ID.
24. Incorporate the executable capabilities delivered by the stale-delivery and child-ownership recovery epics rather than duplicating them. Until a required capability exists, escalate that precise missing capability and retain the incident for later automatic re-evaluation.

## Macro-architecture

The implementation extends the existing supervisor and recovery machinery in five ordered slices. Observation is pure; the audit coordinator selects a proven incident; the existing owning lifecycle capability performs any mutation after a locked fresh recheck. The auditor never becomes a second owner of lifecycle truth.

1. **Canonical observation and incidents.** Extend `cascade/watchdog/health.py`, execution/lease projections, `merged_board`, supervisor readiness, and durable recovery projections. Produce typed observations for Tasks, Features and Epics, including expected waits and unavailable evidence. Canonical tracking repositories own documents, queues, leases and recovery ledgers; registered product worktrees own Git operations. Do not infer identity or authority from path names, parent revisions, cached status or document age.
2. **Independent supervisor lane.** Start an audit coordinator from the supervisor/worker lifecycle before slow ordinary maintenance. It shares existing workspace ownership and shutdown handling but is not called synchronously from `advance_work`, review polling or the watchdog maintenance chain. There is no separate daemon, external scheduler or second dispatch queue. One canonical workspace claim serializes periodic and manual passes across processes. Monotonic deadlines, persisted last-run scheduling data and coalescing avoid duplicate/catch-up execution.
3. **Generation-aware recovery contract.** Extend existing action/orphan/remediation ledgers rather than persisting another board/status database. Each incident carries typed work ID, tier, failure class, concrete accountable owner, relevant authoritative generation, evidence, capability, request/acknowledgement/result, attempt history, cooldown and outcome. Claim leases expire. Only successful completion for the unchanged generation suppresses permanently; claimed/error/refused/deferred/unsafe/no-op rows remain eligible for bounded reassessment. A changed lease, head, queue, validation/checkpoint, document revision, blocker or capability invalidates relevant cached decisions.
4. **Executable adapters.** Reuse `supervisor_recover_task_delivery`, Feature Task recovery, durable action resume/rearm, canonical merge and rollup, team supervision, review-health retry, owned review publication, integration-branch recovery and completion/stacked-review reconciliation. Registration includes allowed failure classes, concrete ownership checks, required evidence, lock/precondition protocol, bounded invocation and durable result path. Startup and per-incident checks verify availability; a missing operation becomes an owned system incident with an exact resume action. An event-only route is not a repair.
5. **Scoped diagnosis and operator view.** Deterministic checks/repairs require no model. A named `health_auditor` role may receive only incident evidence, bounded diagnosis/recovery tools and owned paths needed for an authorized repair. Existing owner teams perform scoped mutation and supervised validation. The War Room consumes the same projection/receipts and sends guarded manual requests to the same coordinator.

### Operational contract

- Configuration: `[automation.health_audit]` with `enabled = true` and `interval = "30m"` when omitted. Duration grammar is a positive integer followed by `s`, `m`, `h` or `d`; supported bounds are 60 through 86,400 seconds inclusive. Reject invalid types/values with an actionable configuration error; isolate audit failure from unrelated delivery. The new switch controls health audits independently of `automation.enabled` and the existing supervisor-health maintenance setting.
- Jitter adds at most the smaller of 5% of the configured interval and 60 seconds. Restarts reconstruct the next deadline from durable scheduling state and admit at most one overdue pass. Wall-clock changes cannot cause a catch-up storm. Manual runs coalesce with an in-flight audit and preserve the periodic deadline; disabling scheduled audits still permits an explicit guarded human run.
- Each pass inspects at most 100 work items and spends at most 60 seconds in observer/coordinator work. A fair continuation cursor covers all tiers and resumes incomplete scans. Every subprocess/network call on the path has an explicit timeout/cancellation bounded by its remaining budget. Long validation, Git repair or model work is handed to existing supervised workers/actions and never blocks the scheduling lane or runs under a global lock.
- Candidate set: all nonterminal work, completed work updated within seven days, and any work referenced by unresolved action, review, publication, reconciliation or cleanup state regardless of age. Pending references cannot age out. A bounded incremental inventory/cursor must avoid repeatedly scanning the entire completed history; restart resumes incomplete coverage.
- No-progress classification requires repeated authoritative observations across at least one configured interval or an existing expired canonical lease/action deadline. A live owner, pending legitimate input/review, human gate or dependency wait is not proof of failure. Unknown evidence is reported as unavailable, never silently healthy.
- Repairs recheck current authority and generation under the appropriate lifecycle lock. Reserve idempotently, release broad locks before I/O, and recheck the relevant heads/evidence before publication. Use existing adapter retry limits; any adapter without a finite policy must declare one before registration. Reaching an attempt cap routes an actionable incident and a bounded future reassessment, not permanent suppression or unlimited model retries.
- Healthy runs have no lifecycle/document mutation, event, model turn, toast, chat, Git commit or success-only external API call. The sole documented observability exception is one compact, untracked supervisor receipt/cursor per completed pass containing schedule recovery state, last/next time, duration and counts. Its storage is outside watched board/queue inputs and cannot dispatch work or notify anyone. Active incidents use existing durable recovery storage.
- Default-on release requires demonstrated Task lost-queue/stale-delivery recovery, Feature owner/publication recovery and Epic owner/closeout recovery through real lifecycle mutations. Foundations may land before adapters, but production default activation is the final integrated slice. Missing capabilities fail closed and re-evaluate later; this does not waive required adapter delivery.

## Cross-module constraints

Extend the existing supervisor health projection, direct-report health sweep, durable action recovery, orphan-delivery recovery, lifecycle locks, and reconciliation commands instead of adding a parallel scheduler or status database. Treat board metadata, durable actions, execution leases, registered worktrees, and forge review state as authoritative according to their existing ownership boundaries. Separate observation from mutation and require a locked recheck before every repair. Agent rights must be capability-based, incident-scoped, auditable, and no broader than the owning team’s safe recovery authority. Preserve user changes, dirty worktrees, accepted history, and human decisions. Run observation in a supervisor-owned lane independent of ordinary advancement/review polling, with bounded I/O and no global lock held across network, provider, test, or Git subprocesses. A recovery adapter is eligible only when its concrete operation and owner routing are registered and testable.

## Core dependencies

Use the installed project runtime and existing supervisor health projection, direct-report sweep, orphan-delivery recovery, durable actions, lifecycle locks, board reconciliation, War Room request protections and `cascade.toml` configuration. The current checkout includes the completed stale-delivery recovery work from `epic_041` and parent-owned child recovery from `epic_042`; consume their executable implementations and regression fixtures, not duplicate algorithms or rely solely on their status labels.

The software dependency manifest declares no additional software or installation requirements for this epic. The owned integration environment already has Python 3.12.8, Git 2.34.1, Node 20.20.2, the declared project libraries and pytest. No dependency installation, upgrade, new service, credentials or provider change is authorized by this plan.

Primary code seams: `cascade/watchdog/health.py`, `cascade/watchdog/config.py`, `cascade/workspace/worker.py`, supervisor readiness/status, `cascade/task/orphan_delivery.py`, `cascade/task/supervisor_recovery.py`, `cascade/task/action_recovery.py`, `cascade/team_supervision.py`, `cascade/review_health.py`, `cascade/team_review_recovery.py`, `cascade/team_branch_recovery.py`, completion reconciliation and War Room routes/static UI.

## Feature breakdown

| Feature | Shippable result | Depends on | Epic criteria primarily owned |
| --- | --- | --- | --- |
| `feat_013_001` — Define canonical audit observations, incidents, and recovery authority | Pure all-tier observation, typed identities, generation-aware incident lifecycle, named scoped role and executable capability contract | None | 3–8, 10–13, 19–21, 23–24 |
| `feat_013_002` — Run bounded health audits in an independent supervisor lane | Strict configuration, independent bounded scheduling, workspace serialization, restart/coalescing, silent receipt and manual-run coordinator | `feat_013_001` | 1–3, 7–8, 12, 14–15, 18 |
| `feat_013_003` — Recover Task delivery incidents through canonical guarded adapters | Lost-queue recovery, lease/pinned resume, stale-evidence revalidation, owner routing and exactly-once merge/rollup | `feat_013_002` | 4, 8–13, 16–17, 19–20, 22–24 |
| `feat_013_004` — Recover stalled Feature and Epic owners and publication lifecycles | Concrete parent owner/dispatch/publication/closeout adapters, gates, escalation and real recovery results | `feat_013_003` | 5–6, 8–13, 17, 19–24 |
| `feat_013_005` — Expose audit controls and prove default-on recovery acceptance | War Room status and guarded run-now, operator documentation, integrated acceptance and final default-on release | `feat_013_004` | 7, 14 and integrated proof of all 24 |

This is a sequential delivery chain, with shared foundations before repair adapters and UI. Each backlog feature contains its own outcome, acceptance boundaries and validation obligations. Feature teams decompose implementation tasks after approval; this epic planning turn does not dispatch implementation.

### Architectural handoff for Feature 001 · 2026-11-08

This guidance implements the approved contract and preserves the five-feature sequence and all 24 criteria. The Feature 001 body was access-restricted; this is an epic/interface review, not approval of that feature plan.

- Preserve a pure observation boundary. `sweep_supervisor_health` currently reconciles blockers and invokes remediation; it cannot serve directly as the new write-free observer. Reuse canonical projections and classifiers while keeping mutation behind the coordinator and guarded adapters. Distinguish expected waits, unavailable evidence and proven incidents explicitly.
- Keep work ID, accountable owner ID, document revision, Git head, branch and incident generation as separate validated fields. Resolve parent identity from canonical metadata and worktree identity from registration. The Task parent revision must never substitute for its Feature ID. Generation inputs must include the relevant lease, queue, evidence, heads, blockers and capability facts, without volatile observation timestamps creating a new incident on every pass.
- Extend existing recovery storage with bounded reassessment; do not inherit `_remediate_if_unchanged`'s unconditional suppression whenever a ledger key exists. Claimed, refused, deferred, unsafe, error and no-op results require expiry/cooldown and changed-generation reassessment. A queued request or owner acknowledgement remains pending recovery until the original lifecycle action has a durable result.
- Specify each adapter's concrete owner, operation, allowed failure classes, required evidence, claim/recheck protocol, timeout/cancellation behavior, finite retry policy and request/acknowledgement/result path. The existing Feature `supervise_child(..., action="recover")` message/wakeup is a handoff primitive, not proof of successful repair. Missing capabilities remain precise incidents for later reassessment; Feature 001 must not advertise adapters reserved for Features 003/004 as executable.
- Preserve canonical lock order: the Task lifecycle helper acquires the shared process lock before the tracking-root file lock. Observer work must not wrap repair dispatch in a broad sweep lock. Adapters reserve and recheck under the owning lifecycle lock, release broad locks before Git/network/provider/validation work, and revalidate before publication. Audit coordination must not introduce a reverse lock dependency or wait for owner completion while holding a lifecycle lock. Cancellation/draining and a changed generation invalidate stale repair authority; durable handoffs must remain recoverable after interruption.
- Foundation validation should exercise silent healthy observation, unavailable evidence, typed owner identity, changed generations and retryable negative outcomes. Features 002–005 retain bounded scheduling, concrete repair mutations and integrated release evidence. Existing helper reuse does not waive their timeout, lock or acceptance obligations. Changes to approved operating bounds, authority, scope or release gates require the amendment protocol.

### Acceptance and scope control

Reuse existing isolated-repository recovery fixtures and the War Room route/JavaScript harness. Validate the new audit entry point through real owner routing, wakeup, acknowledgement, owned-branch mutation, work-defined supervised checks, replacement evidence, matching-blocker clearing and the original merge/review action reaching terminal completion exactly once. Substitute deterministic external model/forge responses where needed; do not mock away recovery callbacks or count queued events as successful repair.

The release evidence must cover the `task_038_002_002` missing pending-index regression, Feature ID versus parent revision, stale-but-live ownership, missing checkpoints, dirty worktrees, conflicts, busy targets, stale evidence, approval/comment gates, orphaned parent planning, split repositories, concurrent manual recovery, crash/restart, invalid/disabled intervals, bounded full candidate coverage, blocked maintenance and a wholly healthy silent pass. Keep existing unrelated sibling/manual blockers and failed attempt history. Targeted integrated tests earn their keep; do not add redundant unit coverage for already exercised adapters.

Excluded: a new scheduler service, status database, notification channel, generic repair console, analytics dashboard, blanket repository permissions, new forge workflow, arbitrary dependency setup or destructive Git automation. None of these exclusions reduces the 24 success criteria.

### Planning validation baseline · 2026-11-08

Command: `python -m pytest -q tests/watchdog/test_health.py tests/task/test_supervisor_recovery.py tests/test_review_health.py`.

Result: 22 passed, 2 failed in 14.13 seconds. The failures were `test_health_sweep_retries_failed_blocked_task_once_through_dispatch` and `test_recovery_failure_is_recorded_once_for_concurrent_and_repeated_sweeps`; both stopped while activating their fixture Epic with `provider_preflight_blocked`, before exercising recovery. This planning change modifies no product code and does not claim a green baseline or completion of new audit acceptance. `feat_013_003` must use deterministic provider-inventory fixtures without weakening production admission and demonstrate both recovery cases; `feat_013_005` must record a passing integrated release suite. No provider change or installation is authorized to work around the fixture failures.

## Open questions

No product-scope questions remain for this revision.

- Existing recovery capabilities are candidates for thin registered adapters; only operations proven executable for the concrete owner may run. Missing or unsafe capability yields precise durable escalation and later reassessment.
- The completion window is seven days, extended without age limit by unresolved durable action/review/publication/reconciliation/cleanup references.
- Task lost-queue and stale-delivery, Feature owner/publication, and Epic owner/closeout adapters must pass actual mutation acceptance before default-on release.
- The Epic Architect must review the shared interfaces, lock/cancellation design and executable adapter coverage and sign off on the resulting current revision. Technical refinements must retain the operational and acceptance contract above.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-11-06 · Human amendment · Make the auditor a configurable health-and-recovery loop for Tasks, Features, and Epics; default to every 30 minutes, remain silent when healthy, and grant incident-scoped repair capabilities when unhealthy.
- 2026-11-07 · Human amendment · Require independent bounded scheduling, executable owner-scoped capabilities, generation-aware retries, and end-to-end proof of actual recovery mutations.

- `dec_001` · 2026-11-08 · Epic Manager · **Scope and delivery sequence**
  Chose Deliver five sequential features: shared health/incident authority, independent scheduling, Task recovery, Feature/Epic recovery, and War Room plus default-on acceptance..
  Rationale: Shared ownership and generation contracts precede executable adapters. Reuse completed Epic 041/042 recovery and existing tests; require actual mutation proof before enabling the integrated audit by default.
  Honors: All 24 success criteria, especially 16, 19, 21–24; no new scheduler service, status database or software installation..

- `dec_002` · 2026-11-08 · Epic Manager · **Audit operating bounds**
  Chose Use strict integer s/m/h/d intervals from 1m to 24h, default 30m; cap jitter at min(5%,60s), each observer pass at 100 items/60s, and retain fair continuation. Health-audit enablement is independent of ordinary automation; manual runs preserve periodic deadlines..
  Rationale: Explicit small bounds make scheduling and cancellation testable without slowing ordinary delivery. Long recovery stays in existing supervised actions. A compact untracked non-dispatching receipt/cursor is the only healthy-run write exception.
  Honors: Criteria 1–2, 7, 14–15 and 18; startup/restart and manual/periodic concurrency must coalesce..

- `dec_003` · 2026-11-08 · Epic Manager · **Completed coverage and safe actionability**
  Chose Inspect completed work updated within seven days plus unresolved action/review/publication/reconciliation/cleanup references of any age. Only proven incidents may repair; expected waits and unavailable evidence are distinguished. Capability and generation checks gate every adapter..
  Rationale: A bounded recent window limits repeated history scans while durable references retain older incomplete delivery. Negative outcomes stay retryable under bounded policies, and missing capabilities remain actionable rather than falsely recovered.
  Honors: Criteria 3–13, 17 and 19–24; approval/comment gates, live owners, dirty worktrees and typed work identity remain protected..

- `dec_004` · 2026-11-08 · Epic Manager · **Acceptance evidence**
  Chose Retain the observed 22-pass/2-provider-preflight-failure baseline; require deterministic provider-inventory isolation and passing real recovery acceptance in the Task and final acceptance features..
  Rationale: Both failing legacy tests stop before recovery at fixture Epic activation. Recording the exact limit avoids confusing an environment-sensitive baseline with proof of the new audit or changing production provider authority to make a test pass.
  Honors: Frugal engineering, criteria 16–17 and 22–24; no redundant test suite or unauthorized provider/dependency change..

- `dec_005` · 2026-11-08 · Epic Manager · **Feature 001 planning handoff**
  Chose Apply the approved epic contract to feat_013_001 without expanding scope: deliver pure canonical Task/Feature/Epic observations, typed work/owner/revision/generation identities, generation-aware incident retry semantics, and the named incident-scoped recovery authority/capability contract. Keep configuration and scheduling in Feature 002, concrete Task repairs in Feature 003, concrete Feature/Epic repairs in Feature 004, and UI plus default-on activation and integrated release proof in Feature 005. Preserve the five-feature dependency chain..
  Rationale: Feature 001 must supply downstream consumers with expected-wait versus unavailable-evidence versus proven-incident classification; concrete accountable owner and capability eligibility; fresh locked recheck requirements; durable request/acknowledgement/result and bounded reassessment semantics. Reuse existing recovery storage and Epic 041/042 operations. Missing capabilities remain precise durable incidents eligible for later reassessment; registering a contract or emitting an event does not establish successful recovery. Focus foundation validation on identity confusion, generation changes and retryable negative outcomes, live-owner/gate safety, and pure healthy observations; retain real mutation acceptance in the adapter and final integration slices. Feature 003 retains the provider-inventory fixture correction and Feature 005 the passing release suite. This is sequencing guidance under the approved contract, not an amendment or a claim to have reviewed the access-restricted Feature 001 body. Any proposed change to epic acceptance, operating bounds, authority or release gates must use the epic amendment protocol before implementation.
  Honors: All 24 approved success criteria; default-on release only after Task, Feature and Epic real lifecycle recovery proof; no new scheduler/status database, broadened mutation rights, dependency installation or provider changes..

- `dec_006` · 2026-11-08 · Epic Architect · **Feature 001 architectural handoff**
  Chose Record the approved foundation contracts and implementation hazards in the epic's architectural handoff: pure observation, typed identities, generation-aware reassessment, executable capability evidence, canonical lock order, cancellation and durable handoff semantics..
  Rationale: Code inspection confirms the existing health sweep mutates lifecycle state, remediation suppresses any existing ledger key, and Feature supervision can provide only message/wakeup evidence. Reuse these primitives selectively without inheriting behavior that violates the approved contract. Feature 001 supplies the shared interfaces; downstream features prove bounded execution and real terminal recovery. Feature 001's body was access-restricted and was not reviewed. This clarifies the approved architecture without changing scope or acceptance.
  Honors: All 24 success criteria; five-feature sequence; real Task/Feature/Epic mutation acceptance before default-on activation; existing provider-fixture follow-up in Features 003/005; no new dependency, provider, scheduler service or status database..
## Amendment log

- 2026-11-06 · Reframed periodic auditors from advisory repository analysis into authoritative lifecycle health detection and bounded recovery. Added the lost merge-queue entry from `task_038_002_002` as a required regression scenario.
- 2026-11-07 · Strengthened the auditor after repeated manual recovery of Tasks 037_002_004, 037_002_005, 037_003_002, and 037_003_005. Added independent execution, retryable negative outcomes, concrete ownership/capability checks, all-tier no-progress detection, and real mutation acceptance tests. Removed duplicated generated brief sections.
