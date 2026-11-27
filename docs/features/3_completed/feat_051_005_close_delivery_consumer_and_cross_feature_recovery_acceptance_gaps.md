---
id: feat_051_005
title: Close delivery-consumer and cross-Feature recovery acceptance gaps
tier: feature
status: completed
parent: epic_051
children:
- task_051_005_001
- task_051_005_002
- task_051_005_003
- task_051_005_004
depends_on:
- feat_051_004
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: c4a7d4a9e72dde65103e04905a45f9cf99eda9c8
created: '2026-11-27'
updated: '2026-11-27'
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
approved_at: '2026-11-27T03:56:12.580901+00:00'
---
# Close delivery-consumer and cross-Feature recovery acceptance gaps

## Parent Epic

epic_051

## Scope

Close the existing Epic delivery-consumer and cross-Feature recovery acceptance gaps without expanding the delivery contract. Preserve the original Feature, branch and review identity, finite recovery budgets, and the separate lifecycle planning-readiness projection.

Reproduce the integrated 95bc9af4 discrepancy with temporary Git and normal configured approval and activation: a completed Feature can have a closed, unverified review with delivery phase merge_verification_pending and blocker accepted_current_generation_missing while feature_review_pending is false and the Watchdog dependency gates return ready. Audit integration-required consumers in cascade/watchdog/dispatch.py, cascade/stacked_dispatch.py and recovery dispatch. Gate execution coherently for closed-unmerged, missing, stale-generation, and accepted-but-not-intended-target-integrated evidence. Preserve supported stacked dispatch; verified intended-target integration releases eligible work once.

Trace a dependent Feature's Task through real supervisor, queued-delivery and recovery paths when its upstream Feature has unchanged red CI. Add only the source-bound observation routing and durable generation fence needed to prevent repeated execution or validation over passes and restart. A material evidence change allows one ordinary gated reevaluation. Unrelated Task failures keep their normal recovery owner. Script external forge or provider transport only at named seams.

Repair the relevant test fixture setup in tests/workspace/test_kickoff.py and tests/test_feature_closeout_flow.py using normal activation and configured approval. Restore assertions that reach idle/no-provider and dependent-feature release. Reuse the late-repair and review-recovery harnesses and bounded Recovery contract gate; avoid unrelated cleanup. The initial integrated run had 24 passes and 17 pre-existing failures: 16 existing_child_work activation refusals and one missing-agent-configuration approval refusal.

Task delivery requires focused tests, owning design reconciliation, source contract and native Structurizr Code views, pinned local render, browser navigation, and explicit limitations. Epic Architect owns final integrated publication. Do not add a scheduler, ledger, provider launcher, second PR for an open review, approval/CI bypass, dependency installation, or deployment.

## Data structures

- The existing Feature delivery projection supplies phase, blocker, evidence status, current review generation, accepted generation, and intended target integration evidence. Consumers use one coherent projection per decision rather than treating a closed review flag as verified delivery.
- Existing Task queued-action metadata retains upstream blocker identity, material evidence generation, matching repair action/generation, and the generation last evaluated. Keep these separate from the Task's own failure classification and attempt history; use the existing action ledger and incident budget.
- No new persistent store is planned. If a source trace shows another existing action field is necessary, document its owner and migration/default behavior in the owning design and task closeout.

## API contracts

- cascade.review.feature_delivery_view/feature_delivery_views are read-only delivery evidence. A consumer that requires completed upstream integration waits unless the relevant current generation is verified on the intended target; lifecycle dependency evaluation continues to answer planning readiness independently.
- cascade.watchdog.dispatch._deps_met and _dependency_review_pending, cascade.stacked_dispatch feature blockers, and relevant recovery dispatch must agree on the same execution prerequisite while retaining the deliberate stacked-dispatch exception.
- cascade.task_rollup.record_upstream_review_observation attaches normalized evidence to the queued actions actually affected across Feature boundaries. retry_pending_task_merges compares the observed and evaluated generations before a claim. Repeated equal evidence spends no provider, validation, merge or recovery attempt; a material change enters the existing gates once.
- Failure gates preserve missing/unknown evidence as waits, exact source and intended target checks, normal approval and activation, and unrelated Task recovery authority.

## Logic flow

~~~mermaid
flowchart TD
    Upstream[Completed upstream Feature] --> Projection[Read current delivery evidence]
    Projection -->|unverified or stale| Wait[Retain dependent execution and queued action]
    Projection -->|verified intended target| Dispatch[Ordinary guarded dispatch]
    Red[Current upstream red CI] --> Observe[Normalize blocker and generation]
    Observe --> Queue[Persist on affected downstream queued Task]
    Queue --> Compare{Generation already evaluated?}
    Compare -->|yes| Wait
    Compare -->|new| Gates[Ordinary dependency and recovery gates]
    Gates --> Attempt[One bounded reevaluation]
    Attempt --> Queue
    Dispatch --> Done[One eligible release]
~~~

## Task breakdown
- task_051_005_004
- task_051_005_003
- task_051_005_002
- task_051_005_001

1. **task_051_005_001 — Close integration-required delivery consumer gates.** Reproduce the closed-unverified discrepancy and map every relevant execution consumer. Implement a coherent gate without changing planning readiness or supported stacked dispatch. Prove closed/missing/stale/target-mismatch waits and one verified release.
2. **task_051_005_002 — Fence cross-Feature Task recovery on upstream evidence.** Trace the actual dependent Task path, route the normalized upstream observation to affected queued actions, and persist the evaluated generation in the existing ledger. Prove unchanged red CI across passes and restart, one material-change reevaluation, verified release, and unrelated failure ownership.
3. **task_051_005_003 — Repair activation fixtures and prove the integrated journey.** Fix the two named fixture files through normal activation and configured approval. Run focused consumer, late-repair, review-recovery and bounded Recovery contract scenarios with real temporary Git and scripted external transports only where needed.
4. **task_051_005_004 — Reconcile design and architecture evidence.** Update owning designs and architecture model, views and source contract against the final diff; validate render, navigation and source links; record exact no-change reasons, measured reuse and remaining limits. Preserve accepted snapshots and revision-pinned publication.

Each later task depends on the preceding task so its acceptance runs against one integrated source state.

## Diagram-impact inventory

| Level and view key | Owner and source symbols | Planned impact and verification |
|---|---|---|
| Landscape/context: cascade-context | cascade/DESIGN.md; existing people, forge and supervisor | Expect no actor or responsibility change. Recheck against final diff and render; update only if an actual boundary changes. |
| Containers: cascade-containers | cascade/DESIGN.md; current runtime and Git/action/checkpoint stores | Expect no runtime or persistence boundary change because the plan reuses existing stores. Verify against final diff and normal/restart trace. |
| Components: cascade-supervisor-components, cascade-team-components | cascade/DESIGN.md, cascade/watchdog/DESIGN.md, cascade/task/DESIGN.md, cascade/feature/DESIGN.md, cascade/boss/DESIGN.md | Reconcile dependency gate, normalized observation, queued Task retry, Feature repair and Boss target verification collaborations. Confirm each edge has one real owner. |
| Code: cascade-watchdog-code | cascade/watchdog/DESIGN.md; dispatch._deps_met, dispatch._dependency_review_pending, review_health.reconcile_open_review_health and affected recovery entry points | Show actual gates and routing symbols with native declaration kinds and pinned source. |
| Code: cascade-task-code | cascade/task/DESIGN.md; task_rollup.record_upstream_review_observation, retry_pending_task_merges and generation comparison; task action ledger entry points | Show source-bound fence, durable action ownership, restart and attempt behavior. |
| Code: cascade-boss-code | cascade/boss/DESIGN.md; boss.view._deps_met and target verification consumer, if touched | Update changed symbols; otherwise document concrete consumer no-change reason after diff review. |
| Code: cascade-feature-code, cascade-workspace-code, cascade-epic-code | respective owning DESIGN.md; Feature repair, activation/approval and Epic dispatch symbols only if touched or newly needed for navigation | Review each affected symbol/owner. Do not invent changes for unchanged modules; state specific reason in closeout. |
| Behavior | Owning Watchdog, Task, Feature and root designs | Trace normal release, closed/unverified wait, unchanged-red restart and material-change retry with source-linked Mermaid flows. |

For every changed Code node, keep architecture model.dsl, views.dsl and workspace.contract.json synchronized, with cascade.codeComponent, cascade.parent, cascade.sourcePath, cascade.sourceSymbol, and native element kind. Verify context-to-Code Explore, Level up, deep-link restoration, opening pinned source, stale/deleted symbols, component ownership, bounded pinned rendering and warm artifact reuse. Review DESIGN.md prose for stable IDs, one requirement/decision owner, resolved links and no delivery history. Record design paths reviewed, checks and gaps in Task closeout; no DESIGN.md edits exist at planning time.

## Risks & upward questions

The current Task observation selector only finds queued Tasks owned by the observed Feature; cross-Feature routing must be demonstrated from the actual supervisor path before changing ownership logic. A broad dependency gate could incorrectly block deliberate stacked execution, so gate tests must distinguish intended stacking from required target integration. No upward contract amendment is currently needed.

## Decision log

- Keep lifecycle planning readiness distinct from execution delivery evidence. Execution consumers requiring integration read current delivery evidence; the existing dependency evaluator retains its planning semantics.
- Reuse queued Task action metadata and incident budgets for cross-Feature fencing. Do not introduce a new scheduler or persistence store.
- Sequence consumer gate, downstream fence, fixture/integrated evidence and final architecture reconciliation to keep verification tied to the integrated diff.

- `dec_001` · 2026-11-27 · Feature Architect · **Decision log**
  Chose Keep lifecycle planning readiness distinct from execution delivery evidence..
  Rationale: Execution consumers that require integration need current delivery evidence, while dependency_evaluation.py remains the planning-readiness contract.
  Honors: epic_051 dec_010; existing Feature delivery contract.

- `dec_011` · 2026-11-27 · Feature Architect · **Decision log**
  Chose Reuse queued Task action metadata and incident budgets for cross-Feature fencing..
  Rationale: The existing ledger already persists blocker and evaluated generations across restart and bounds recovery attempts; only affected downstream selection and routing need expansion.
  Honors: epic_051 dec_008 and dec_009; REQ-TASK-DELIVERY-003.

- `dec_012` · 2026-11-27 · Feature Architect · **Decision log**
  Chose Sequence consumer gate, downstream fence, fixture and integrated evidence, then final architecture reconciliation..
  Rationale: Each acceptance stage can verify the integrated source state and the last stage can reconcile model, contract and design against the final diff.
  Honors: epic_051 success criteria 1, 4 and 6; design skill closeout contract.

## Closeout

Completed child work: `task_051_005_001` (Gate integration-required consumers on current Feature delivery evidence), `task_051_005_002` (Fence dependent Feature Task recovery on upstream review generations), `task_051_005_003` (Repair activation fixtures and prove the integrated recovery journey), `task_051_005_004` (Reconcile integrated design and navigable C4 delivery evidence).
