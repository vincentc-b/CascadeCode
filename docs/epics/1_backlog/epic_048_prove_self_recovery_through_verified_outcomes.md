---
id: epic_048
title: Prove self recovery through verified outcomes
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-11'
updated: '2026-11-11'
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

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use Codex as the brief's provider and preserve its explicit per-role model/reasoning settings for descendants. Keep this brief in backlog for normal review and activation; filing it does not authorize implementation or activation of a new team.

Reuse and connect the existing action ledger, generation/claim machinery, review and resolution admissions, owner-scoped tools, supervisor update/deployment, audit investigations and receipt projection. Avoid a parallel scheduler, recovery database or unrestricted agent capability. Prioritize a narrow executable vertical journey and its regression before extending the matrix.

Preserve current approvals, human decisions, dependency gates, scoped writes, protected files, execution leases, exact revision checks, source/target ownership and leased publication. An agent must not repair a timeout by shrinking required acceptance coverage, editing protected global settings, granting itself authority, changing an approved runtime deadline or directly publishing unreviewed work.

Keep historical failures, decisions, evidence, superseding generations and original incident identities. Bound subprocess output and persistence costs without deleting history just to make the dashboard look healthy. UI reads and cached snapshots must not grant repair authority. Never expose credentials, provider prompts or private reasoning in artifacts.

The existing operator incident repair and PR 234 are baseline evidence, not a substitute for implementation of the complete contract. Inspect current code and merged history before minting new work; retain existing valid fixes and avoid duplicate late-repair or dashboard work already owned by Epics 047 and 044. A newly discovered unrelated product acceptance defect must be routed through its own approved owner and review flow.

Likely boundaries: `cascade/review_health.py`, `team_review_recovery.py`, `review_rebase.py`, `review_validation.py`, `validation_command.py`, `resolution_actions.py`; `cascade/task/action_recovery.py` and final validation/delivery; Epic/Feature recovery and team supervision; `cascade/watchdog/` audit, investigations and recovery; workspace kickoff, ownership, update/deployment and retirement; API/War Room recovery projections; the recovery journey tests and CI workflow. These are investigation entry points, not a requirement to rewrite every component.

Document material-generation identity, role and policy authority, legacy migration, claim/restart semantics, process cancellation, exact checked/published/deployed revisions, independent verification, expected external waits and test coverage. Keep scoped review validation and full product acceptance truthful and distinct.

Budget policy and extensions must be owned by the approved repository/operator authority. A recovering agent cannot increase its own limits, select weaker required checks or reclassify an exhausted incident to obtain new allowance. Keep limits and attribution consistent across deterministic executors and paid owner/auditor turns, and document any provider-specific enforcement limits before claiming a hard token or monetary cap.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which existing capabilities complete the first executable owner-agent recovery journey, and where are the actual missing authority or deployment transitions?
- Which validation profiles and budget adaptations can be pre-authorized safely, and which changes genuinely require a policy owner or human review?
- How will the harness prove the running worker loaded the reviewed repair instead of exercising only an isolated branch or a mocked postcheck?
- Which legacy exhausted/partially published states can be reconciled from unambiguous evidence without resetting history?
- What reviewed default and maximum model-turn/token/runtime allowances fit each repair class, and which authority can grant a bounded extension?
- How will shared agent turns and providers with unavailable usage be attributed honestly without creating an accounting or retry loophole?

## Decision log

- 2026-11-11 · Human · Requested a durable self-recovery contract and regression after the Epic 046 failure; approval is pending PR review and merge.

## Amendment log

_(none)_
