---
id: epic_048
title: Prove self recovery through verified outcomes
tier: epic
status: active
parent: null
children:
- feat_048_001
- feat_048_002
- feat_048_003
- feat_048_004
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-11'
updated: '2026-11-24'
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
# Prove self recovery through verified outcomes

## Intent

Make self recovery an executable, tested delivery contract rather than a recurring diagnosis or a team wakeup. For a recoverable incident with satisfied approval boundaries, the supervisor and owning teams must detect it, admit a scoped repair, execute it, validate the exact result, publish through the normal review route, independently verify the durable postcondition, and close the original incident. When an actual external decision is required, name that prerequisite and its owner without retrying an impossible action indefinitely.

### Incident: Epic 046 review recovery exhausted itself

Investigation on 2026-11-11 found PR [232](https://github.com/vincentc-b/CascadeCode/pull/232), `epic/epic_046` into `main`, still conflicting remotely while its owned checkout already contained a local merge resolution. The accepted recovery admission observed source `4d79b053e3c423ffc8bb89f02475d401eb8c545f` and target `878e6bfc501554084d130f84dfe4053b822d46a6`, under `resolution:v1:d51756077124dc260301490974925dccb34be8073c461f76ef0625c2f73791f2`. Commit `c9272a882ffd7b5fa0887229354b3ba3eba4a556` preserved both dependency declaration and architecture publication tool contracts and the corresponding template script versions. The resolved code was not published.

The publication gate read the full repository default `python3 -m pytest -q` from the product trunk, with a 300-second review timeout. The owner agent could resolve its checkout and run focused tests but had no authority to change product-trunk validation policy. It reported this precise prerequisite. `reconcile_open_review_health` nevertheless kept calling `publish_team_review_resolution` because the local branch was clean and contained both admitted heads. That wrapper treated the same local resolution as a new owner decision each time. One hundred attempts timed out from approximately 06:05 to 15:04 UTC; the action reached its attempt bound and became blocked. Repeated sweeps and reports did not make the configured validation feasible.

The hundred recorded attempts were local `pytest` executions, not evidence of a hundred model calls. At the configured 300-second timeout they consumed roughly 8 hours 20 minutes of validator runtime, spread over approximately nine hours of elapsed time. Separate agent investigation/recovery turns consume tokens, but the incident records do not retain reliable per-incident token totals or a monetary bill. Do not infer model charges from tool-attempt counts, equate compute time with tokens, or report unknown token usage as zero.

Exhaustion left another trap: the wrapper had already recorded and resolved an owner decision for attempt 101 before discovering that no attempt remained. Rearming the action reused this already-resolved decision identity, leaving it in `awaiting_owner_decision` without executing. A live operator retry exposed this even after a first generation-fencing fix. A regression reproducing the exact legacy decision ID failed before the additional fix.

Existing review tests passed because they replaced repository validation with trivial commands, including empty Python programs. They proved parts of admission and push wiring, but not the production command/budget mismatch, unchanged repeated failures, legacy budget exhaustion, restart persistence or verified recovery completion.

### Retry and resource budget policy

Recovery needs both operation-specific retry limits and a cumulative resource budget for the whole incident. An unchanged deterministic failure stops after its first failed attempt until relevant evidence changes. Genuine transient failures get a small configured limit, initially at most three total attempts, with increasing delays and jitter. The previous generic hundred-attempt limit is inappropriate for this publication operation; a more specific approved policy must justify any larger limit.

Material evidence changing can make another attempt meaningful, but must not replenish the incident's overall budget. Account for cumulative tool attempts, validator/process runtime, wall-clock duration, paid model turns and observed model input/output usage across recovery generations, restarts, parent escalations, periodic investigations, provider changes and linked follow-up actions. Changing an ID, making a cosmetic commit, issuing another wakeup or cycling between policies must not create an unlimited retry or token allowance.

Persist consumption and enforce admission before another expensive process or model turn starts. Distinguish local checks from model calls. Record provider/model and actual token usage when available; label estimates and unavailable usage honestly and retain safe turn/time limits when exact provider usage cannot be established. Define in-flight reservations, concurrency behavior and how provider-enforced output limits or cancellation bound overshoot; do not claim a strict token cap for a provider that cannot enforce or expose it. A monetary amount may be shown only from trustworthy usage/rate or billing evidence.

When a budget is exhausted, stop automatic spending and emit one actionable escalation with the original failure, cumulative attempts/runtime/known usage, last evidence, work preserved, next safe action and the authority required for any extension. Preserve the incident as unresolved or waiting; budget exhaustion is neither successful recovery nor permission to discard delivery. Extensions require an explicit authorized decision with a reason and additional bounded allowance, retain all earlier consumption, and cannot be self-granted by the retrying team. The broader briefing/audit schedule must not keep commissioning paid reviews of that same exhausted incident without new evidence or authority.

### Related findings and operational resolution

- Generic recovery can inspect an incident or wake its owner without supplying the capability or authority needed to change its blocking prerequisite. A delivered recovery request and repeated `repair_requested` reports are not executable repair work or success.
- Review validation policy is distinct from product acceptance. The investigation also found three stale planning test fixtures that omitted the now-required dependency declaration. They were repaired by declaring their intended normal planning state; production dependency checks were not disabled.
- A mutable source head or check policy can move while validation runs. Publication must use the tested immutable commit and recheck the governing policy, admitted remote heads and lease immediately before changing a remote branch.
- `main` advanced to `0859eade8d980fb03dcc8a82c370ab586945829d` during operator repair. Recovery had to merge that current target and obtain a fresh admission, rather than reuse the old remote-head authority. The supervisor claimed the new run while a foreground caller was also inspecting it; a running claim is an expected pending outcome, not another failure.
- The actual new publication action, `resolution:v1:4032ad37671e9b03a9ffb410f4402acf186059916a863e947440a556975e2dbe`, passed 113 configured review checks and published tested source `97314f7d53b0b91eeed0dd9a6346ab0719701794` in one attempt. PR 232 subsequently merged. The original hundred failed attempts remain recorded; fresh forge evidence reconciled the old incident rather than deleting or resetting it.
- A companion implementation [PR 234](https://github.com/vincentc-b/CascadeCode/pull/234) adds material-generation retry fencing, generation-specific decision IDs, bounded review-specific validation policy, timeout diagnostics, immutable tested-head publication, and a Recovery contract CI workflow. Its real-process/local-remote journey covers timeout cleanup, restart, legacy exhaustion, human-gate refusal, and source/policy races. This is a concrete publication-path repair, not proof that the full owning-agent self-repair journey works.
- At investigation time, periodic Epic 046 findings also distinguished missing A10 epic-page browser proof and a 180-second renderer default from an approved 90-second contract. Do not equate review publication, merge metadata, a green scoped regression gate or an operator hotfix with proof that every product acceptance criterion was satisfied. Reassess those findings independently with current evidence.

This brief complements [Epic 047](epic_047_recover_late_repair_delivery_after_feature_completion.md), which covers late-child/terminal-parent lifecycle recovery, exact mutation ownership and descendant-safe retirement. Retain its requirements rather than duplicating them. Coordinate with Epic 021's convergence proposal, existing action recovery and parent delivery work in Epics 040-042, and Epic 044's audit projection. The gap here is an end-to-end, deployable and continuously verified self-recovery contract across those components.

### Success criteria

1. Define and enforce one observable recovery contract: detected, admitted, assigned, executing, validating, publishing, verifying, resolved, or waiting on a named external prerequisite. Reuse existing action identities and receipts. Team wakeup, message acknowledgement, a local commit, a passing helper test, `reported_fixed`, parent completion and remote publication each prove only their own stage. Resolution requires fresh independent evidence that the original blocking condition and required delivery obligation are satisfied.
2. Separate expected waits from executable repairs and missing capabilities. Every repair-requested incident must resolve to an accountable actor, a reachable scoped operation, its permitted inputs, and a durable result or precise refusal. If a tool is absent or the blocking prerequisite belongs to another owner, route a deduplicated executable repair/policy handoff; do not repeatedly wake a team that cannot act. Preserve legitimate human approval, installation, credentials, comments and scope-change boundaries.
3. Admit retries against material evidence: the actual local repair revision, admitted source and target heads, selected approved validation policy and relevant environment/capability revision. An unchanged deterministic failure must not trigger another expensive attempt, consume the remaining budget, create another decision or generate repeated agent work. Genuine transient retries require the bounded policy and cumulative allowance in criteria 16-18. Ignore clock-only changes, observation order and report timestamps. Recheck material drift at execution and publication boundaries.
4. Preserve complete attempt and decision history when a genuine repair or authorized policy/environment change makes an exhausted action executable. Give the new generation a bounded opportunity only while cumulative incident allowance remains or an authorized bounded extension has been recorded, without resetting counters, erasing failures or manufacturing success. Use decision identities tied to their recovery generation, not only an attempt number that may already have a resolved decision. Define conservative handling of legacy records lacking generation evidence; do not silently reopen unrelated terminal or human-gated incidents.
5. Make validation policy executable and owned before work is admitted. Distinguish full Task validation, bounded review-conflict regressions and Epic product acceptance. Profiles must identify their command, coverage, budget, owner and approval/version, with upper bounds and retained diagnostics. An agent may select only pre-authorized applicable profiles or request the correct policy owner; it must not reduce checks, extend a product SLA, alter protected trunk config or skip approval merely to obtain green output. Detect an infeasible command/budget combination early and route it once.
6. Bind every green result to the immutable tested commit, parent/target revision and governing policy. Preserve useful bounded stdout/stderr on timeout or failure, identify which gate failed, and stop the entire validator process group before resuming work. Source or policy movement during checks invalidates that result. Publication must push the tested SHA with fresh authority and the correct remote lease, never an untested moving HEAD. A changed remote target requires a fresh admission, not an unchecked retry.
7. Make recovery survive worker restarts, repeated manual/periodic requests and concurrent owners. One action generation has one live claim and at most one downstream publication effect. Distinguish running/pending claims from failed repairs in tool/API/UI results. Reconcile a remotely completed effect before replaying it after interruption. Handle crashes before claim, during tests, after local commit, immediately after push and before the completion receipt without losing work or falsely declaring resolution.
8. Establish a supported bootstrap/deployment route for repairs to the orchestration code that is blocking its own delivery. Track the reviewed/integrated revision, loaded worker revision and capability generation. A fix stranded in a Task/Feature branch or copied into one operator's dirty checkout is not a durable deployed recovery capability. Avoid requiring the broken stage to be its own only repair route; retain the normal review and authorization boundaries and expose any genuine external approval prerequisite.
9. Add a deterministic integration harness using the production worker/watchdog queues, role-scoped tool catalog, parent supervision, recovery admission, Task tests/commit/delivery, review publication and authoritative postchecks. A scripted provider/forge transport may replace external paid or network services, but it must invoke normal production tool adapters and receive their real refusals/results. Use real temporary repositories, a bare remote, real validator processes and the actual durable stores. Do not mock repair, testing, publication or final verification as successful, call a raw ledger-success setter, or hand-edit lifecycle state to make the journey pass.
10. The positive acceptance journey must inject a genuine recoverable failure, let the owning team diagnose and repair through its available tools, validate the repaired immutable revision, publish, independently inspect the remote and deployed/current state, and close the original incident without operator Python, direct pushes or manual state edits. An eligible incident must reach that verified outcome within stated time/work/attempt budgets. Assert no duplicate worker, Task, review, message or publication under repeated sweeps and concurrent callers.
11. Reproduce Epic 046's timeout and exhausted-decision sequence through the harness: unchanged checks time out once and stay paused across a new worker process; a permitted policy-owner correction or approved profile change admits exactly the needed next attempt; old attempts and already-resolved next-attempt decisions remain intact; real checks and leased publication succeed; independent remote and incident evidence proves completion. Cover an unavailable policy owner with a bounded actionable wait rather than a false success or another hundred attempts.
12. Include negative and interruption scenarios: actual red tests, insufficient budget, malformed policy, policy/head changes during validation, stale admissions, competing remote updates, dirty/uncommitted work, live execution owners, wrong-team scope, missing capabilities, denied approvals/credentials and unavailable evidence. A real external gate must remain closed with the correct owner and next action. Failed checks or unverifiable receipts must never resolve the incident or weaken the future gate.
13. Include a cross-stage journey for Epic 047's completed-parent/late-repair case, plus correct worktree ownership and descendant persistence after retirement. Test split product/tracking roots and a repair to a recovery adapter itself. Assert the board, execution record, pending delivery, owning parent, review registry, deployed capability and historical incident agree after publication, cleanup and restart. Review success must not conceal unfinished product acceptance or unintegrated follow-up heads.
14. Run the deterministic recovery contract automatically for relevant PRs and main changes, with a named check, bounded runtime and retained failure evidence. Keep the existing real publication regression from PR 234 and expand it to the actual owner-agent journey. Demonstrate that breaking retry deduplication, bypassing validation, publishing the wrong SHA, omitting final verification or losing a completion receipt causes a test failure. Provide a documented local command and fresh-workspace setup; do not rely on an optional manual smoke test or an empty validator command.
15. Demonstrate the contract on a controlled real supervisor incident through supported UI/agent entry points, retain exact revisions, commands, budgets, actor/decision identities, process restart points, remote/deployment proof and unresolved prerequisites, and record what the harness cannot simulate. Do not claim autonomous self recovery from green unit tests alone. Completion requires both the repeatable CI regression and the supported operational recovery evidence.
16. Enforce operation-specific retry policy and a cumulative incident-wide resource budget in addition to material-generation fencing. Unchanged deterministic failures pause after one failed generation; transient failures default to at most three total attempts with exponential backoff and jitter. Set reviewed defaults and explicit maximums for expensive tool attempts, paid repair/investigation turns, token usage where enforceable, validator/process runtime and elapsed incident time. A new generation or linked child/action does not silently renew the overall allowance.
17. Attribute and persist consumption across the original incident and its recovery/escalation lineage. Separate test/process attempts from model invocations, retain actual provider/model usage when available, avoid double-counting cached tokens or shared accounting, and distinguish known, estimated and unavailable consumption. Reserve bounded allowance before concurrent expensive work starts and reconcile actual use afterward. If exact token usage or a hard provider limit is unavailable, report that fact and enforce conservative model-turn/runtime limits; never invent a zero usage or a reliable bill. Budget and claim state must survive worker restart.
18. At budget exhaustion, prevent new automatic tool/model work and coalesce further periodic observations into one durable, accountable escalation. Expose consumption, preserved work, the unresolved blocker and the authority/decision needed to continue. An authorized extension must record its actor, reason, relevant new evidence, added bounded allowance and prior consumption; it must neither reset history nor let the same team approve its own spending increase. Unrelated eligible work should continue normally.
19. Add CI regressions proving that an unchanged failure consumes one expensive attempt; transient failures stop at their configured cap; model turns stop at the paid-work allowance; concurrent workers cannot overspend one reservation; and restart, a new generation, cosmetic revision, provider switch, policy cycle or replacement action cannot reset the incident budget. Exercise exhausted incidents receiving repeated audit requests, unknown provider usage, in-flight overrun/cancellation, refused extension and an explicitly authorized bounded extension. Independently assert process/model invocation counts and retained consumption, not just a returned paused status.

## Macro-architecture

### Baseline and smallest delivery slice

This is a proposed implementation plan, not evidence that the complete contract already exists. The owned checkout contains the publication fixes described in the brief, late-child Feature repair, generation-bound parent postchecks, descendant-safe retirement, and bounded audit projections. Retain those implementations. The initial verification command `python -m pytest -q tests/test_review_recovery_journey.py tests/workspace/test_c4_source.py` passed 20 tests in 20.58 seconds during planning.

Concrete gaps found in source:
- `task/action_recovery.py:admit_review_publication_generation` can grow `attempt_bound` to `attempt_count + 1` for a new generation. It has no incident-wide consumption ceiling. Preserve generation-specific decision IDs while making the cumulative allowance a separate mandatory gate.
- `agent/types.py:RoleResult` carries outcome and recovery report but no normalized usage receipt. `agent/recovery_contract.py:report_provider_recovery` describes provider-turn completion, which must never become incident resolution.
- `watchdog/audit_investigation.py:request_investigation` and replay retain generation/cooldown evidence, but need shared incident-budget admission before another paid owning-team turn.
- `workspace/worker.py:_worker_supervisor_status` reports process/status facts without a binding to the loaded reviewed source/artifact. The README operator handoff is a useful starting route, not deployed-capability proof.
- `tests/test_review_recovery_journey.py` exercises real validation and publication, but the end-to-end worker/owning-agent/tool/deployment journey remains to be established.

First deliver a bounded real publication recovery against the existing machinery, then extend that same harness to the actual owning-agent journey, then deployment/cross-stage recovery, then the full negative matrix and operational proof. Do not postpone all integration until the final feature.

### Responsibilities and durable contracts

| Boundary / source entry points | Proposed change and evidence owner |
|---|---|
| `watchdog/incidents.py`, `reservations.py`; `task/action_recovery.py:start_attempt, resume_action, admit_review_publication_generation` | F1 adds stable original-incident lineage and atomic reservation/settlement using existing durable stores and lifecycle locks. Action/generation identity remains distinct from budget identity. |
| `team_review_recovery.py:publish_team_review_resolution`; `review_rebase.py:check_and_publish_review_rebase`; `review_validation.py:run_review_validation` | F1 gates expensive checks and retains exact tested source, target, policy and remote lease; F2 supplies executable owned validation profiles and scoped handoff. |
| `watchdog/audit_recovery.py:dispatch_audit_recovery`, `audit_investigation.py:request_investigation, replay_pending_investigations`; `workspace/kickoff.py:deliver_queue_kickoffs` | F2 joins observation, capability, actor, queued work and result; unchanged or exhausted incidents cannot repeatedly commission model work. |
| `agent/graph_turn.py:run_planning_role_turn`, `agent/adapter.py:run_role`, `agent/types.py:RoleTurn, RoleResult`; `task/swe_turn.py:run_swe_turn_sync` | F2 reserves before every incident-related provider invocation and persists attributable provider/model/usage/time receipts across restart. Role catalogs and path/approval guards retain authority. |
| `workspace/launcher.py:run_launcher_loop`, `workspace/worker.py:run_worker, drain_and_shutdown`; capability registry and health evidence | F3 binds reviewed/integrated/installed/loaded revisions and capability generation; supported restart and bootstrap retain independent installation authority. |
| `watchdog/incident_postcheck.py:reconcile_parent_lifecycle_incident`, `reservations.py:verify_incident_postcheck`; review registry, pending delivery and worktree registry | F2/F3 independently verify original obligations from authoritative state. Publication alone never clears product acceptance or an unfinished descendant delivery. |
| Existing audit projection and War Room consumers | F2 projects typed stage, wait, budget and prerequisite evidence through the current bounded read interface. Reads neither initiate work nor grant extensions. F4 verifies truthful presentation. |

Proposed logical receipt fields: stable incident/lineage ID; action and generation IDs; stage; owner/capability and authority revision; exact work/repository identities; source/target/policy/environment revisions; invocation/reservation/claim/decision IDs; observed result and retained evidence references; independently verified obligation; wait reason, next action and accountable external owner. These extend existing envelopes, not a parallel lifecycle state machine/database. The owning feature specifies schema/version compatibility before Task dispatch.

Stages are detected → admitted → assigned → executing → validating → publishing → verifying → resolved. Any stage can enter waiting with a named prerequisite. A failed attempt is retained beneath the unresolved incident. Fresh material evidence returns through admission; it does not rewind consumption or erase history. A live claim is pending. An interrupted process is reconciled from process identity, durable receipts and remote effects before replay. Unknown evidence remains waiting/unverifiable.

### Incident budget policy proposed for plan approval

These are initial product defaults and configuration ceilings, not installation/spending authority for this planning turn. Approval must preserve full Task and Epic acceptance coverage. A workload that cannot fit must wait for its policy owner; it must not substitute weaker validation.

| Resource | Default allowance | Maximum configurable allowance without a separately reviewed policy change |
|---|---:|---:|
| Unchanged deterministic failure | 1 failed expensive attempt per material generation | 1 |
| Transient retries for one operation | 3 total attempts | 3; any larger operation-specific limit requires explicit reviewed justification |
| Expensive tool/process attempts across incident lineage | 6 | 20 |
| Paid repair/investigation role turns across incident lineage | 6 | 12 |
| One validator/process operation | Existing approved timeout, normally 300 s, further bounded by reservation | 3,600 s; never increase an approved profile automatically |
| Total validator/repair subprocess runtime | 1,800 s | 7,200 s |
| One model turn / cumulative model runtime | 300 s / 1,800 s | 900 s / 7,200 s |
| Elapsed incident time from original admission, including waits | 3,600 s | 86,400 s |
| Known provider input plus output tokens | 200,000 | 1,000,000; hard enforcement only where the provider can bound admitted input/output |
| Concurrent expensive operations per incident | 1 | 1 for the initial implementation |

Transient delays use 5 s then 10 s exponential bases with bounded ±20% jitter; persist the next eligible time. Test with an injected clock/random source while invoking real operations. Clock-only changes do not change material identity. No retry after exhausted cumulative allowance even when a transient delay has elapsed.

Reserve one attempt/turn and its bounded worst-case runtime before launch under the existing cross-process lock. Check the remaining elapsed deadline and reduce the permitted runtime accordingly. Settle the unique operation once from actual observations; retain consumed reservation conservatively when process/usage evidence is unknown. A proven dead claim may be reconciled; a nominal lease timeout alone cannot free a live claim. Cancellation must reap local child processes, retain partial usage and describe provider-side overrun limitations.

Token ceilings are admission/stop thresholds unless both usage and enforceable bounds are supported; do not promise a hard cap for Codex or another provider without evidence. Unknown usage is unknown, with conservative turn/time ceilings still mandatory. Cached input is a subset of input, and total usage is not the sum of overlapping provider counters. Prefer one recovery incident per provider turn. Shared turns require a predeclared allocation across participating incident lineages, reservations on all of them, one physical invocation receipt and exactly-once accounting; ambiguous attribution waits rather than obtaining free work.

Use one deduplicated exhaustion escalation containing original failure, known cumulative consumption, unknown usage, last material evidence, preserved work and next action. An extension requires authenticated independent operator/repository authority, actor, reason, relevant evidence, added finite allowance and retained prior totals. The recovering team cannot authorize its extension. New IDs, provider changes, policy cycles and parent handoffs cannot renew limits. Unrelated incidents remain eligible.

### Validation, deployment and completion boundaries

A validation profile owns its exact command, coverage class, source/target applicability, policy owner/approval revision, per-run budget and diagnostics. Distinguish Task validation, review-conflict regression and Epic acceptance. Known infeasible profiles or a repeated deterministic timeout wait for the policy owner. Source/policy/target movement invalidates prior green evidence and requires fresh admission. Keep whole-process-group cleanup and bounded diagnostic tails.

The harness uses real temporary product/tracking repositories, a bare remote, real validator processes, normal worker/watchdog queues, graph/checkpoint storage and production scoped tool adapters. Only paid provider and external forge transports may be scripted. Fixture setup may create initial failure/legacy evidence; after admission, no private success setter, lifecycle-file rewrite or direct push may complete the journey. Independently count provider invocations, process spawns and downstream effects.

For runtime repair, separately identify accepted review, integrated commit, installed artifact/source and actually loaded worker process/capability generation. Use the supported drain/restart route, retaining installation approval. If the broken adapter prevents normal admission, the supported independent bootstrap route must expose the exact approved external step; it cannot depend solely on calling that adapter again. F3 must identify the operational target and required authority before F4 runs a live exercise. The local prerequisite manifest proves tooling only.

### Diagram-impact inventory and ownership

Authoritative source directory: `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/` (`workspace.dsl`, `model.dsl`, `views.dsl`, `workspace.contract.json`). Existing integrated views are the starting point, not proof that the new contracts are covered. All rows require final-diff reconciliation. F1–F3 feature planners must copy applicable rows into Task acceptance criteria; F4 verifies the integrated result.

| Level / view keys | Owning design and real source boundaries | Required update / verification and delivery owner |
|---|---|---|
| Landscape/context: `cascade-landscape`, `cascade-context` | `DESIGN.md`; existing operator, local Cascade, forge, provider and renderer boundaries | No new system is proposed: budgets/harness stay inside existing boundaries. Epic Architect checks operator extension/bootstrap responsibility and changes relationships only if needed; F4 verifies context navigation. |
| Containers: `cascade-containers` | `DESIGN.md`, `cascade/DESIGN.md`; CLI launcher, worker, repository artifacts | No extra deployed service or recovery database. F3 documents installed/loaded revision and persistence boundary; change view descriptions/relationships if actual responsibility changes. Verify no claim that C4 containers provide OS isolation. |
| Components: `cascade-supervisor-components`, `cascade-team-components`, affected `cascade-cli-components` / `cascade-war-room-components` | `cascade/DESIGN.md` plus Agent, Watchdog, Task and Workspace designs; source entries in the responsibilities table | F1/F2 expose admission → provider/tool execution → authoritative postcheck; F3 exposes runtime handoff. Preserve one owner per concern; model relationships agree with source and child designs. |
| Code: `cascade-task-code`, `cascade-watchdog-code`, existing publication owner coverage | `cascade/task/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/DESIGN.md`; action generation, reservations, review validation/publication, postchecks | F1 adds real budget/claim/settlement/extension implementation entries and publication collaborators to the correct owning component. If a new focused custom view is needed, declare and connect its exact key in the feature plan; do not leave publication as a documentation-only box. |
| Code: `cascade-agent-code`, `cascade-teams-code`, affected `cascade-epic-code` / `cascade-feature-code` / `cascade-task-code` | `cascade/agent/DESIGN.md` and tier designs; run_role, run_planning_role_turn, run_swe_turn_sync, recovery contracts and scoped dispatch | F2 shows pre-launch reservation, normalized usage, cancellation, provider/tool wiring and receipt consumers. Real paths/symbols/kinds, correct cascade.parent and cascade.codeComponent required. |
| Code: `cascade-workspace-code`, affected `cascade-workspace-commands-code` | `cascade/workspace/DESIGN.md`; run_launcher_loop, run_worker, drain_and_shutdown, owner/retirement interfaces | F3 covers loaded-revision identity and normal/bootstrap restart; link exact state/checkpoint owners. Preserve current descendant ownership and retirement implementation. |
| Code/UI: `cascade-dashboard-code`, affected `cascade-war-room-http-code` | `cascade/war_room/DESIGN.md`; existing recovery/audit projection readers and health routes | F2/F3 update only changed producer/consumer interfaces. F4 verifies budget/stage/wait truthfulness. No audit dashboard redesign. |
| Supplementary behavior | Task/Agent/Watchdog/Workspace owning designs, parent links in `cascade/DESIGN.md` | F1: reserve/run/settle/exhaust/extend; F2: observed incident through owner tools to verification and unavailable-owner wait; F3: review/install/load/postcheck and crash-after-push resume. Mermaid supplements native integrated views. F4 traces one normal and one failure/restart case per changed boundary. |

Proposed ownership of new stable IDs: `REQ-RECOVERY-BUDGET-001` and `DEC-RECOVERY-BUDGET-001` in `cascade/task/DESIGN.md`; `REQ-AGENT-RECOVERY-001` and `DEC-AGENT-RECOVERY-001` in `cascade/agent/DESIGN.md`; `REQ-CASCADE-RECOVERY-002` in `cascade/DESIGN.md`; `REQ-WORKSPACE-RUNTIME-001` and `DEC-WORKSPACE-RUNTIME-001` in `cascade/workspace/DESIGN.md`. These are reserved proposed owners, not implemented requirements. Link existing `REQ-ROOT-AUDIT-003`, `REQ-REVIEW-PUBLISH-001`, `REQ-WATCHDOG-REPAIR-001`, `REQ-TASK-DELIVERY-002`, `REQ-WORKSPACE-OWNER-001` and `REQ-WORKSPACE-RETIRE-001`; do not duplicate them.

Architect review before plan sign-off must establish source-linked proposed structure and resolve required integrated publication/budget coverage. Reconcile current designs without claiming planned behavior exists. Final acceptance includes source-contract validation, real pinned-image rendering, context → container → component → Code, Level up, saved deep links and pinned source opening; verify renamed/deleted symbols and ownership changes, warm artifact reuse and measured performance without per-view process startup or weakened bounds. Accepted snapshots remain immutable.

## Cross-module constraints

Use Codex as the provider and preserve the explicit per-role model/reasoning settings for descendants. Human activation authorizes planning; feature execution remains behind normal plan approval. New prerequisite installation and live runtime changes retain their separate exact authority boundaries.

Reuse and connect the existing action ledger, generation/claim machinery, review and resolution admissions, owner-scoped tools, supervisor update/deployment, audit investigations and receipt projection. Avoid a parallel scheduler, recovery database or unrestricted agent capability. Prioritize a narrow executable vertical journey and its regression before extending the matrix.

Preserve current approvals, human decisions, dependency gates, scoped writes, protected files, execution leases, exact revision checks, source/target ownership and leased publication. An agent must not repair a timeout by shrinking required acceptance coverage, editing protected global settings, granting itself authority, changing an approved runtime deadline or directly publishing unreviewed work.

Keep historical failures, decisions, evidence, superseding generations and original incident identities. Bound subprocess output and persistence costs without deleting history just to make the dashboard look healthy. UI reads and cached snapshots must not grant repair authority. Never expose credentials, provider prompts or private reasoning in artifacts.

The existing operator incident repair and PR 234 are baseline evidence, not a substitute for implementation of the complete contract. Inspect current code and merged history before minting new work; retain existing valid fixes and avoid duplicate late-repair or dashboard work already owned by Epics 047 and 044. A newly discovered unrelated product acceptance defect must be routed through its own approved owner and review flow.

Likely boundaries: `cascade/review_health.py`, `team_review_recovery.py`, `review_rebase.py`, `review_validation.py`, `validation_command.py`, `resolution_actions.py`; `cascade/task/action_recovery.py` and final validation/delivery; Epic/Feature recovery and team supervision; `cascade/watchdog/` audit, investigations and recovery; workspace kickoff, ownership, update/deployment and retirement; API/War Room recovery projections; the recovery journey tests and CI workflow. These are investigation entry points, not a requirement to rewrite every component.

Document material-generation identity, role and policy authority, legacy migration, claim/restart semantics, process cancellation, exact checked/published/deployed revisions, independent verification, expected external waits and test coverage. Keep scoped review validation and full product acceptance truthful and distinct.

Budget policy and extensions must be owned by the approved repository/operator authority. A recovering agent cannot increase its own limits, select weaker required checks or reclassify an exhausted incident to obtain new allowance. Keep limits and attribution consistent across deterministic executors and paid owner/auditor turns, and document any provider-specific enforcement limits before claiming a hard token or monetary cap.

## Core dependencies

Canonical software manifest revision 2 is ready: all 15 entries have current successful read-only verification. The target is explicitly the local Linux x86_64 verification host `ip-172-31-37-14`, runner/repository/worktree `/home/ubuntu/dev/CascadeCode`, host sandbox, runtime `/opt/conda/bin/python3.12`, container digest `not_applicable`. Source editing is confined to the owned integration worktree `.cascade/worktrees/epic_epic_048`; the dependency executor's repository identity is not a deployed-runtime claim.

Verified versions: CPython 3.12.8; PyYAML 6.0.3; cursor-sdk 1.0.37; langgraph 1.2.14; langgraph-checkpoint-sqlite 3.1.1; pytest 9.0.3; setuptools 80.9.0; Playwright 1.64.0; Git 2.34.1; Node 20.20.2; Docker 28.0.0; Codex CLI 0.172.0; gh 2.4.0+dfsg1; Chromium 156.0.8078.4; Structurizr image pinned by `cascade/workspace/c4_render.py` to `sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`. Exact installed artifact/RECORD hashes and check recipes live in the canonical manifest; installed hashes do not claim upstream package provenance.

No installation was performed or authorized. Credentials, live forge access and exact deployment target remain separately checked operational prerequisites. CI must declare its own resolved runner/tool identity and reproducible setup in F4; this local verification is not proof of a future hosted runner. F3 must update declarations before any different environment or newly required software is used.

Existing late-parent recovery, ownership, postcheck and audit-projection code is an integration dependency, not duplicate feature scope. Preserve its current contracts and route unrelated acceptance defects to their existing owner. Inspect later integrated changes before descendant implementation; do not assume a historical PR or completed status alone proves conformance.

## Feature breakdown
- feat_048_004
- feat_048_003
- feat_048_002
- feat_048_001

The Epic Team will create and sequence feature plans here.

## Open questions

- **Epic Architect, before plan sign-off:** validate proposed budget defaults/ceilings and reservation/lineage ownership; establish the source-linked design proposal and exact integrated publication/budget Code-view coverage. Inspect affected parent/child interfaces and remove any delivery-history wording in touched designs. Manager must review any resulting plan revision before signing it.
- **F2, before provider Task dispatch:** record each supported provider's actual usage and enforceable limit/cancellation capabilities. The approved fallback is turn/time admission with honest unknown usage; no hard token-cap or monetary claim without evidence.
- **F3 → F4, before controlled operational execution:** identify the exact target environment, reviewed runtime/artifact, supported bootstrap steps and independent operator/install/credential authority. Absence is a visible completion blocker, not permission to deploy or call private repair functions.
- **Legacy migration:** known preserved attempts remain charged; ambiguous lineage/usage waits for a bounded independent decision. Neither migration nor an accepted historical PR grants a fresh allowance.

### Planning design review and evidence

Reviewed root `DESIGN.md`, `cascade/DESIGN.md`, and affected sections of `cascade/{task,watchdog,workspace,agent}/DESIGN.md`, the architecture README/views, and concrete source entry points listed above. Current baseline source validation and publication journey: 20 passing tests in 20.58 s. Installed renderer image and real Chromium launch were verified as prerequisites; no new model render, browser navigation proof, operational self-recovery demonstration or final product acceptance is claimed.

No DESIGN.md or C4 source edits are included in this manager turn. The current Agent design is materially too shallow for the proposed usage/reservation/cancellation boundary and contains baseline-inventory attribution; the Architect must reconcile that affected design and integrated views before plan sign-off. Publication/budget Code coverage and the deployed-revision contract also require an explicit proposal review. These are routed architectural review gaps, not waived deliverables. The inventory above assigns implementation and final verification to the feature teams. Designs must describe current reconciled behavior without delivery chronology; this work record owns proposals, review state and evidence.

## Decision log

- 2026-11-11 · Human · Requested a durable self-recovery contract and regression after the Epic 046 failure; approval is pending PR review and merge.

- `dec_001` · 2026-11-24 · Epic Manager · **Scope and sequencing**
  Chose Deliver four dependent slices: durable incident budgets; bounded owning-agent recovery; reviewed/loaded runtime and cross-stage proof; adversarial CI plus controlled operational evidence..
  Rationale: The repository already contains immutable review publication, material-generation fencing, late-child repair and audit postchecks. Extend these boundaries and their real-process harness instead of duplicating lifecycle owners. Establish an executable vertical journey before expanding the negative matrix.
  Honors: Success criteria 1–19; smallest shippable vertical slice; no parallel recovery scheduler/database; preserve Codex and explicit descendant model/reasoning settings..

- `dec_002` · 2026-11-24 · Epic Manager · **Budget and authority proposal**
  Chose Separate material-generation retry admission from one persistent incident-wide allowance. Propose bounded defaults/maxima in the epic table for independent architect and human plan review; no automatic renewal or self-approved extension..
  Rationale: admit_review_publication_generation currently grows attempt_bound for a new generation. A separate lineage reservation gate is required before tool/provider spending. Unknown provider usage remains unknown with conservative turn/time limits; independent authenticated authority owns explicit extensions.
  Honors: Success criteria 3–4 and 16–19; preserved attempt/decision history; no self-granted spending, weaker validation or invented token/billing evidence..
## Amendment log

_(none)_
