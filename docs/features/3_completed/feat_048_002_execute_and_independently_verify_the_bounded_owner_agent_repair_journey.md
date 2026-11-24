---
id: feat_048_002
title: Execute and independently verify the bounded owner-agent repair journey
tier: feature
status: completed
parent: epic_048
children:
- task_048_002_001
- task_048_002_002
- task_048_002_003
- task_048_002_004
depends_on:
- feat_048_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: ffcb9a105c823708d76cd7ba9734bcecbb570eec
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  feature_lead: high
  feature_architect: high
  swe: medium
approved_at: '2026-11-24T19:16:22.540240+00:00'
---
# Execute and independently verify the bounded owner-agent repair journey

## Parent Epic

epic_048

## Scope

This feature joins the existing Task-owned incident budget to paid provider launches, accountable owner tools and independent Watchdog verification. The first deliverable is one executable positive journey; the later matrix protects that journey across retries, restarts and denied gates.

## Outcome
An admitted incident reaches a real accountable owning team, which diagnoses, repairs, tests, commits, delivers and publishes through its scoped tools; a fresh authoritative postcheck alone resolves the original incident. Every paid repair/investigation turn consumes the F1 allowance before provider launch.

## Scope and ownership
Connect existing worker/watchdog queue, audit investigation outbox, parent supervision, tier graphs/tool catalogs, provider adapters and review publication. Extend cascade/agent/types.py, adapter.py and provider adapters only as required for attributable invocation evidence and bounds. The scripted transport harness must run through production tool adapters and receive actual refusals. Establish one executable positive journey before expanding the matrix.

## Acceptance criteria
- Epic criteria 1–7, 9–12 and 16–19: observable stage receipts distinguish detected/admitted/assigned/executing/validating/publishing/verifying/resolved/waiting. Acknowledgement, reported_fixed, provider finished and remote push cannot stand in for verification.
- Resolve each repair to actor, capability, permitted inputs, authority revision and durable result. Missing tools or policy owner cause one executable handoff or precise external wait. Genuine human/installation/credential/comment/scope gates remain closed.
- Validation profiles identify command, coverage class, owner, approval/version and finite budget. Task, review and epic acceptance remain distinct. Preflight declared feasibility and retained timeout evidence; never learn feasibility by unbounded repeats. Select only applicable approved profiles.
- Before provider start reserve a model turn and worst-case time from the original incident, including audit/briefing and parent/replacement-action paths. Capture provider/model/invocation ID and known/estimated/unavailable usage; cached tokens are a subset, not additive usage. No invented token total or bill. Provider cancellation and enforceable output limits bound supported overshoot; unknown usage retains conservative turn/time charging.
- A canonical invocation receipt is settled exactly once across callbacks/restarts. Prefer one recovery incident per turn; shared turns require predetermined lineage allocation and reservations for every participating incident, with one physical invocation record and no double-counted global usage. Ambiguous attribution cannot create free paid work.
- Extend the integration harness through real worker/queue/checkpoint/role-scoped tool dispatch, Task test/commit/delivery, owner publication and independent remote/postcondition observation. Script only external paid-provider/forge transport. Retain real red checks and process-group timeout cleanup.
- Replay the timeout + legacy exhausted next-decision sequence through the owner tools, with an approved policy correction and authorized extension where required. The unavailable-owner variant stops with the owner and next action.
- Paid-work budget exhaustion blocks repeat audit/investigation commissions but leaves unrelated work eligible. Test direct/manual/periodic/provider-switch entry points, denied extension, authorized extension and duplicate dispatch concurrently.

## Designs and diagrams
Own proposed REQ-AGENT-RECOVERY-001 / DEC-AGENT-RECOVERY-001 in cascade/agent/DESIGN.md and link F1's budget authority. The cross-stage receipt interface is proposed REQ-CASCADE-RECOVERY-002 in cascade/DESIGN.md; watchdog owns postchecks, not provider adapters. Reconcile cascade/{watchdog,epic,feature,task}/DESIGN.md plus affected War Room projections. Update cascade-agent-code, cascade-watchdog-code, cascade-teams-code, affected epic/feature/task code views, supervisor/team component views, and dashboard code only if its producer/consumer interface changes.

## Required Task acceptance contract

Feature planners must copy the applicable epic diagram-impact rows into Task acceptance criteria and budget that work with the implementation. Preserve existing requirement owners; proposed new IDs become current design facts only after implementation is reconciled. Update owning DESIGN.md, model.dsl, views.dsl and workspace.contract.json together when structure changes. Native custom Code views must link real source symbols and declaration kinds, support context → container → component → Code, Level up, deep links and pinned source. Include normal and failure/restart flows, persistence, authority and process isolation limits. Verify source contracts, supported local rendering and representative browser navigation; record actual evidence and gaps in work records. Do not rewrite accepted architecture snapshots.

Use production tool adapters, durable stores and real temporary repositories/processes for integration proof. Scripted external provider/forge transport is permitted; fake successful repair, validation, publication or final verification is not. No raw success setters or lifecycle-file edits to force progress. Tests must count effects independently. Keep product acceptance separate from review validation. Preserve Codex and the parent's explicit role/model/reasoning assignments. No dependency installation or live deployment is authorized by this feature.

## Integrated F1 authority and API

F1 is integrated here at completed revision `ff3cd399d1523ba6c4e123825c811f8c0b700e7c`; its reservation implementation is `270a72a2`. `cascade/task/incident_budget.py` is the sole authority for `REQ-RECOVERY-BUDGET-001` and `DEC-RECOVERY-BUDGET-001`. It stores `incident_budgets` with actions in tracking-root `.cascade/executions.json` under `task_lifecycle_lock`. F2 consumes and extends this API, without a second ledger.

| F1 operation | Exact contract |
|---|---|
| `bind_incident_budget(incident_id, action_id, generation, evidence, *, root, now=None)` | Bind original or linked action/material generation; ambiguous legacy evidence waits. |
| `reserve_incident_operation(incident_id, operation_id, kind, worst_case, claim_id, policy_version, *, root, now=None)` | Atomic `IncidentOperationDecision`: admitted/pending/exhausted/owner_decision, reason, policy version, optional receipt/permit. Replay returns pending and the old receipt. Current version is 1. |
| `settle_incident_operation(incident_id, operation_id, observation, *, root, now=None)` | Idempotent settlement; observation carries `usage`, `quality` known/estimated/unavailable, `outcome` success/error/timeout/interrupted/unknown, optional `failure_class`, `claim_complete`. Interrupted/unknown charges reservation and waits. |
| `read_incident_budget(incident_id, *, root)` | Read restart-safe projection without minting allowance. |
| `extend_incident_budget(incident_id, authenticated_authority, reason, evidence, finite_additions, *, root, now=None)` / `record_incident_budget_exhaustion(incident_id, reason, *, root, now=None)` | Independent authenticated human, finite additions within trusted maxima; one durable exhaustion escalation. |

F1 dimensions: `tool_attempts`, `paid_turns`, `process_seconds`, `model_seconds`, `elapsed_seconds`, `known_tokens`. `elapsed_seconds` is the original admission deadline, never a reservation. Provider waiting for an MCP/validator call still consumes model time. Task 001 extended the same Task-owned ledger to keep one provider reservation open over a serialized same-claim child operation, with a competing caller pending. Successful provider usage marked unavailable retains the reserved paid turn and time conservatively; prelaunch refusal has zero charge. Task 003 must prove this through the real owner journey and restart.

## Data structures

- Recovery turn: original incident ID, action ID/material generation, checkpoint, top-level claim ID, provider operation ID, physical invocation ID, policy version, receipt ID. A provider switch, new generation or replacement cannot mint allowance.
- Invocation receipt: provider/model, launch/settlement, elapsed time, known/estimated/unavailable input and output tokens, cached input tokens as a subset, usage quality, timeout/output/cancellation capabilities and failure evidence. Settle one physical invocation once across callback/restart. Shared turns need predeclared lineage allocation and reservations for all incidents.
- Stage receipt: original obligation, actor, scoped capability/input, authority revision, immutable source/target/policy, durable result and verification reference. Only independent Watchdog postcheck resolves.
- Validation profile: exact command, coverage class, policy owner, approval/version, applicability, feasibility and finite time/attempt limits. Task, review and product acceptance stay distinct.

## Provider capability and launch-route matrix

| Route | Current source-backed capability and limitation | Required admission/refusal |
|---|---|---|
| Codex CLI (`run_codex_role`, `run_subprocess_turn`) | MCP help/config checked. `RoleResult` has text/status, no normalized usage. Default timeout 3,600 s kills only direct process. SWE uses `workspace-write`; `yolo` bypasses sandbox. Native shell is outside MCP guards. No proven output-token, descendant or remote-spend bound. | Reserve before spawn; enforce finite incident deadline and descendant/process-group policy; check native shell route. Refuse unsupported recovery mode. Treat missing usage as unavailable. |
| Claude CLI (`run_claude_role`, `run_subprocess_turn`) | Strict MCP config when supported; same direct-process timeout/text result; no normalized usage or proven output-token/remote/descendant bound. Native shell permission remains provider-controlled; `yolo` bypasses it. | Same reservation, deadline and shell check; refuse if controls cannot be enforced. Do not claim a strict token cap. |
| Cursor SDK (`_run_cursor_role`) | Custom tools/MCP return text/status only. Built-in tools can remain enabled with custom tools; `yolo` disables SDK sandbox. No per-turn timeout, normalized usage, enforced output cap, descendant or remote cancellation bound is established. | Verify finite deadline and tool/shell capability before launch, or refuse this incident recovery mode. Preserve unavailable usage. |
| Scripted transport (`run_fake_role`) | Deterministic in-process seam can invoke supplied tools; it proves no paid usage or remote cancellation. | Run bounded scripted provider through production Agent dispatch and scoped MCP/tool adapters; count physical calls separately from receipts. |

MCP hosting alone does not constrain provider-native shell, children or remote work. Every expensive route needs enforceable admission/deadline evidence or a precise non-launch refusal. Keep the assigned Codex provider and role/model/reasoning choices.

## API contracts

1. Planning, SWE, audit/briefing, manual/periodic, parent and replacement paths pass original lineage and claim to Agent. Before every incident-related provider start, reserve one paid turn and finite worst-case model seconds, plus any proven known-token bound. Missing lineage, unsupported route, pending claim, exhausted allowance or owner decision returns a typed non-launch result. Pre-spawn setup failure releases/settles the same reservation with evidence; uncertain post-launch work stays charged.
2. Providers return one physical invocation ID and usage quality. Cached tokens remain a subset of input; absent usage is never zero by invention and no bill is displayed without trustworthy rates. Timeout, cancellation, lost response and restart settle/reconcile the exact receipt once. Provider completion is only turn evidence.
3. Provider → production MCP → real validator uses one top-level claim and separate serialized operation receipts. Reserve nested tool/process work before launch and settle before the next nested operation; keep enclosing model-time reservation. A competing caller stays pending. Native shell cannot bypass admission.
4. Watchdog/parent persist actor, capability, permitted inputs, authority and stage outcomes; missing capability/policy owner yields one executable handoff or named wait. Exhaustion coalesces paid audits while unrelated work proceeds. Human, installation, credential, comment and scope gates remain closed.
5. Publication retains immutable tested SHA, fresh source/target/policy authority and remote lease. Watchdog independently re-observes the original blocker and delivery before resolution.

## Logic flow

```mermaid
sequenceDiagram
    participant W as Watchdog / queue
    participant T as Task incident budget
    participant A as Agent / tier runner
    participant M as Production MCP
    participant V as Real validator / review
    W->>T: Bind original incident/generation and claim
    W->>A: Assign owner/capability/authority/checkpoint
    A->>T: Reserve paid turn and worst-case model time
    alt Admitted and bounded route
        A->>M: Provider invokes scoped production adapter
        M->>T: Reserve nested attempt/process on same claim
        T-->>M: Permit; competing caller pending
        M->>V: Real check/repair/publication
        V-->>M: Durable result and immutable delivery
        M->>T: Settle nested receipt
        M-->>A: Result or precise refusal
        A->>T: Settle physical invocation once
        W->>W: Fresh independent original-obligation postcheck
        W-->>A: Resolved or named wait
    else Pending/exhausted/unsupported/owner decision
        T-->>A: Existing receipt or one escalation; no launch
        A-->>W: Wait with owner and next action
    end
```

Restart reads original lineage, checkpoint, claim and receipts before resuming. Lost responses do not authorize replay. Unknown work stays conservatively charged and waits for reconciliation; independent finite extension retains prior use and history.

## Diagram-impact inventory and ownership

| Level and view keys | Source-backed impact | Task owner and verification |
|---|---|---|
| Landscape/context: `cascade-landscape`, `cascade-context` | No new person, external system or responsibility boundary is planned. The harness uses the existing provider, forge and operator boundaries. Reconcile against final diff, especially extension authority and scripted external transport. | task_048_002_001–004 each record a final-diff no-change reason or update relationships; task_048_002_004 verifies navigation. |
| Containers: `cascade-containers` | F1's tracking-root executions sidecar and existing worker/CLI remain the persistence/runtime boundaries. No new service or database is planned; C4 containers do not assert OS isolation. | task_048_002_001–004 reconcile actual storage and process changes and update descriptions if needed. |
| Components: `cascade-supervisor-components`, `cascade-team-components`; affected `cascade-cli-components`, `cascade-war-room-components` | Show budget admission, provider/tool execution, owner publication and Watchdog postcheck with one owner per contract. | task_048_002_001 owns provider/budget edges; 002 owns owner/postcheck routing; 003/004 reconcile final flow and projection consumers. |
| Code: `cascade-agent-code`, `cascade-task-code`, affected `cascade-epic-code` and `cascade-feature-code` | Bind prelaunch reservation, normalized provider usage, exact-once settlement and tier callers to real symbols, declaration kinds and owning components. | task_048_002_001 updates Agent/Task and affected tier designs, model.dsl, views.dsl, workspace.contract.json and verifies source contract/render/browser path. |
| Code: `cascade-watchdog-code`, `cascade-teams-code`, affected tier and `cascade-dashboard-code` | Bind audit/queue admission, scoped repair, review validation/publication and fresh postcheck; dashboard code changes only if its interface changes. | task_048_002_002 updates owning designs and model/contract; 003 traces real positive and failure/restart journey; 004 reconciles matrix and final diff. |
| Supplementary behavior | Show normal reserve→repair→publish→verify and unavailable owner, timeout, cancellation, lost receipt and restart. Document persistent state, authority and process isolation limits. | Each Task updates the owning DESIGN.md for changed behavior; 003/004 run source-contract, pinned local render, Context→Containers→Components→Code, Level up, deep-link and pinned-source checks. |

## Task breakdown

- **task_048_002_001 — provider admission and receipts.** Reserve against the original incident before every paid launch, including audit/briefing and parent/replacement paths. Settle one physical provider invocation exactly once across callback/restart; record provider/model/ID, known/estimated/unavailable input/output/cached usage, cancellation and enforceable output bounds. Unknown usage consumes conservative turn/time. Verify nested MCP and competing caller. Own Agent design and code-view update; preserve Task budget ownership.
- **task_048_002_002 — owner routing and verification contract.** Bind actor, scoped capability, inputs, authority, approved validation profile and durable stage results; stop repeated paid audit commissions at exhaustion. Keep real gates closed and route missing capability/policy owner once. Watchdog alone resolves from a fresh independent postcheck. Own cross-stage, Watchdog, Teams and affected tier/component/code-view updates.
- **task_048_002_003 — first real owner journey.** Drive production queue/checkpoint/tool adapters, Task test/commit/delivery, owner immutable-SHA publication and independent remote/postcondition inspection in temporary repositories. Replay timeout and legacy exhausted decision through restart, approved correction/extension and unavailable-owner wait. Reconcile sequence and integrated code views against the implemented path.
- **task_048_002_004 — adversarial matrix.** Count model/process/remote effects independently across manual/periodic/audit/parent/provider-switch/replacement paths, concurrency, restarts, red checks, drift, denied gates and extension decisions. Verify one escalation, retained consumption and unrelated progress. Reconcile all changed designs, C4 levels and integrated Code views against the final diff.

Dependencies: 001 → 002 → 003 → 004. Tasks 001, 002 and 003 are completed and merged as `ce8c6fe726c422a853c8065bec48474a06a40aa7`, `5291b0bb702eb2f48fefdbbc5940723ee416af55` and `3ce39c19645dad2791692456f6a81af80658752e`. Task 004 is active. Task 001's acceptance contract remains in this Feature record and its implementation notes because its completed Task record still contains placeholder fields. Tasks 002–004 have explicit Task acceptance criteria. Each implementer must retain the applicable diagram row above in Task closeout and update source-linked design only when implementation is real.

## Risks & upward questions

- Provider transports differ in usage and enforceable output/cancellation controls. The Task 001 capability matrix reports those limits; Task 004 must verify paid-turn/time bounds and unavailable-usage accounting across the remaining launch paths.
- A scripted transport must still enter the production adapter and receive actual scoped refusals; Task 003's merged journey exercises the production Task tool path; Task 004 must close the remaining timeout, postcheck closure and launch-route matrix evidence.
- Task 001 was delivered with a `TBD` acceptance, test plan and scope section and a broken Parent Feature link in its completed canonical record. The Feature `revise_task` tool accepts only backlog, ready or blocked Tasks, so it cannot repair that completed record. The board lifecycle owner must supply a supported completed-record correction path; do not edit lifecycle files or change status to force a revision.

## Planning design review

Reviewed `DESIGN.md`, `cascade/DESIGN.md`, `cascade/agent/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/epic/DESIGN.md`, `cascade/feature/DESIGN.md`, `cascade/war_room/DESIGN.md`, and `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}` against integrated F1 source and the F2 planning diff. The affected source declarations, six F1 dimensions, refusal states, provider tool/timeout paths, persistence and restart limits were inspected. `git diff --name-only ff3cd399 HEAD` shows no change to those designs or the model; no current architectural behavior changed in this planning edit. Proposed Agent and cross-stage requirements remain work-record proposals until Task implementation reconciles them with source. `git diff --check HEAD~5 HEAD` passed. No render, browser navigation or runtime journey was claimed as planning verification.

After Task 001 merged, I reviewed `cascade/DESIGN.md`, `cascade/agent/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/epic/DESIGN.md`, `cascade/feature/DESIGN.md`, the provider/ledger source, and the affected `cascade-agent-code` and `cascade-task-code` declarations and contract. The merged Agent design now links the real admission, receipt and settlement symbols and states the local cancellation and remote spending limits; the Task design describes same-claim child serialization and durable settlement. Landscape/context and container boundaries are unchanged because this diff adds no actor, deployed runtime, data store or external dependency. Component and Code relationships changed for Agent-to-Task budget use, with native source-linked nodes. The focused provider, budget, C4 source-contract and render checks passed (`43 passed`); `git diff --check` passed. The browser test still stops at the existing one-click detail expectation, so full Context→Containers→Components→Code, Level up, deep-link and pinned-source interaction evidence remains open for Tasks 002–004. The completed Task 001 record still has `TBD` acceptance/test/scope and a broken Parent Feature link; `revise_task` disallows completed Tasks. This is a board-record correction gap for the lifecycle owner, not an implementation claim. Architecture publication remains the separately owned recorded terminal failure and is not claimed resolved here.

After Task 002 merged, I reviewed `cascade/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/epic/DESIGN.md`, `cascade/feature/DESIGN.md`, the changed Watchdog/Teams source, and `cascade-watchdog-code` and `cascade-teams-code` in the model, views and source contract. Stage receipts now record actor, capability, permitted inputs, authority revision and durable result; Watchdog alone appends resolution after its fresh authoritative postcheck. Owner work binds to the original Task incident budget, while review publication selects a finite approved validation profile and checks feasibility before process spawn. The diff adds no actor, external dependency, deployed runtime, data store or communication boundary, so landscape/context and container views remain accurate. The component/code additions link real Watchdog budget binding and stage receipts and the Teams validation profile to source declarations. Focused Watchdog, review-publication, C4 source-contract and render checks passed (`76 passed`); `git diff --check` passed. The full browser Context→Containers→Components→Code, Level up, deep-link and pinned-source interaction is not yet verified; Task 003 retains that acceptance. Task 003 also owns the real repair/publication/postcheck journey and timeout/restart proof. No architecture publication recovery or completed Task 001 record correction is claimed.

After Task 003 merged, I reviewed `cascade/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/watchdog/DESIGN.md`, the changed Boss merge, review, Task rollup and Watchdog postcheck/projection code, `tests/test_late_repair_convergence.py`, and the Task Code-view additions in `model.dsl`, `views.dsl` and `workspace.contract.json`. The merged flow now binds the original Task allowance before advertising queued merge, reapplies the immutable validated pair when an existing queue entry completes, removes the exact superseded Feature path before review pinning, and requires the Epic target copy to close after accepted publication. The new `queue_task_merge` Code node links a real Function to the Task component and its budget/action collaborators. No actor, deployed runtime, store or communication boundary changed in this diff, so landscape/context and container views remain accurate. The focused journey and C4 source/render checks passed (`31 passed`); `git diff --check 5291b0bb..HEAD` passed. The new journey test scripts the provider and forge, invokes production Task tools, runs a real red then green validator, checks one publication and calls the original-obligation postcheck. It does not itself show a full timeout/legacy-exhaustion replay, Watchdog resolution through `verify_incident_postcheck`, or browser Context→Containers→Components→Code, Level up, deep-link and pinned-source interaction. Task 004 must provide or report those exact evidence gaps along with the adversarial matrix. Task 001's completed board-record correction and separately owned architecture-publication recovery remain open.

## Decision log

- `dec_001` · 2026-11-24 · Feature Lead · **Provider-turn attribution**
  Chose Scope each paid recovery turn to one original incident by default; permit a shared turn only with predetermined lineage allocation and reservations for every participating incident before launch.
  Rationale: One physical invocation and one canonical settlement prevent unallocated paid work and double-counted global usage while preserving F1's single incident-budget authority.
  Honors: Epic 048 criteria 16–19, F1 REQ-RECOVERY-BUDGET-001, Feature 002 paid-work and exact-once receipt acceptance.

- `dec_002` · 2026-11-24 · Feature Lead · **Recovery launch admission**
  Chose Admit an incident-related provider turn only when its complete native-shell, child-process, MCP and remote route has a finite enforceable deadline and a prelaunch F1 reservation; otherwise return a precise non-launch refusal..
  Rationale: The current Codex and Claude helper kills only the direct process after a 3,600-second default, Cursor has no per-turn timeout here, and no adapter returns normalized usage or proves a strict output/remote cap. An MCP tool-host check alone cannot bound native work.
  Honors: Epic 048 paid-work bounds and provider capability constraints; F1 REQ-RECOVERY-BUDGET-001; Feature 002 provider matrix and Task 001 acceptance..

## Closeout

Completed child work: `task_048_002_001` (Meter and settle every incident-related provider turn), `task_048_002_002` (Route bounded incidents through accountable owner tools and independent postcheck), `task_048_002_003` (Prove one real owner-agent repair and legacy timeout recovery journey), `task_048_002_004` (Exercise budget, refusal and concurrency matrix across all launch paths).
