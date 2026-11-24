---
id: feat_047_004
title: Prove late repair convergence and document reviewed runtime handoff
tier: feature
status: completed
parent: epic_047
children:
- task_047_004_001
- task_047_004_002
depends_on:
- feat_047_003
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 39558b2cb130000418f59b6a2683fc28c7038d56
created: '2026-11-18'
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
approved_at: '2026-11-24T05:38:26.840377+00:00'
---
# Prove late repair convergence and document reviewed runtime handoff

## Parent Epic

epic_047

## Scope

## Outcome and scope
Demonstrate the complete late-repair workflow through real lifecycle boundaries, preserve the existing GitHub CLI compatibility fix, and provide a supported handoff for updating a supervisor whose running code blocks reconciliation. Owns epic criteria 11, 13–15 and final cross-feature acceptance; preceding features still own their focused tests and designs.

## Compatibility and runtime handoff
The current cascade/tracking.py::merge_request_snapshot already requests commits instead of unsupported headRefOid and extracts commits[-1].oid; retain it. Existing tests/test_tracking_find.py and tests/test_review_health.py assert query fields. Strengthen contract coverage with a real installed CLI-supported query/response shape, pinned source SHA, empty/malformed commits and moving-head refusal as relevant. Preserve merge SHA, mergeability, comments, descriptions and GitLab normalization. Do not introduce a CLI upgrade or claim a new repair of already-fixed code.
Document and exercise the supported reviewed deployment handoff: identify reviewed source and expected running revision, drain/stop through existing operator controls, update/start from the reviewed checkout through supported installation/start procedures where separately authorized, and record the executing revision plus post-restart review-health result. When old code cannot admit the repair, expose that exact operator prerequisite and retain delivery. No internal Python invocation, manual lifecycle/event edits, runtime hotpatch or claimed deployment from a local merge.

## End-to-end acceptance
Build temporary-repository scenarios using normal mint, dispatch, supervised final validation, queued delivery, parent supervision, review-health and watchdog admission. Forge boundaries may use contract-accurate deterministic transport, while CLI schema compatibility has separate actual-binary evidence.
Reproduce active/open-review and already-merged-review repair, plus repair racing closeout. Existing Task identity and validated work survive. Show the follow-up review covers the later source head and correct target, not merely successful Task merge.
Cover source and target movement, stale generations, live owners, dirty/missing checkout, changed owner, comments/approval/dependency refusals and split roots using shared high-signal scenarios rather than a combinatorial duplicate suite.
Include the misleading sibling completed copy and retirement with a missing last terminal child elsewhere. Restart workers and run repeated sweeps. Assert one durable repair, no falsely active queue/incident, coherent execution/board/rollup, preserved original and follow-up review facts, and discoverable terminal descendants after retirement.

## Task planning and evidence
Budget two cohesive Tasks: end-to-end convergence matrix and CLI/deployment contract coverage; a separate architecture/UI verification Task only if it has material implementation work. Do not create tests mirroring every helper.
Before completion run the configured bounded publication safeguards for any conflict resolution, focused affected suites, the complete scenario matrix, and architecture source-contract validation plus supported real rendering. Record exact commands, revisions, outcomes, any baseline failures and unperformed external gates. A mocked success result or team wakeup is not end-to-end evidence.

## Architecture closeout
Reconcile the epic's full diagram inventory against final code: model.dsl, views.dsl, workspace.contract.json; root/package and owning Workspace, Feature, Boss, Watchdog, Epic, Task, Board/War Room designs as affected. Preserve accepted snapshots.
Verify actual UI traversal context→containers→components→Code, Level up, deep-link restoration and pinned source for representative recovery/ownership/retirement nodes. Test stale renamed/deleted symbols and wrong component ownership. Record cold/warm timings and reuse of the bounded single-batch renderer; no per-view startup or universal latency promise.
Record concrete unchanged-level reasons and unresolved review/deployment prerequisites. Keep delivery history in work records and current architecture in designs. Inherit exact epic role/provider settings.

## Data structures

The Task identity and execution/validation history remain stable across repair. A Feature repair action binds feature ID, request ID, generation, registered owner, source/target heads, authorization receipt and selected child. The review registry retains the accepted generation and a separate pending generation for later code. Terminal-retirement proof binds the parent checkout, required terminal descendants and surviving provenance. Tests inspect these records through public lifecycle operations; they do not write synthetic success rows.

## API contracts

| Boundary | Contract for this Feature |
|---|---|
| `cascade/feature/repair.py::feature_repair` and `cascade/feature/recovery.py::recover_task` | Admit or resume one generation-bound repair under current ownership and safety gates; replay is idempotent. |
| `cascade/task/supervisor_recovery.py::supervisor_recover_task_delivery` and Task final validation | Preserve durable delivery and prior attempts; moved heads require synchronization and a new green validation pair. |
| `cascade/review.py::ensure_feature_review` and `reconcile_feature_review_completions` | Publish to the current target and verify current forge heads. A merged prior review remains history; later source requires a linked follow-up review. |
| `cascade/workspace/integration_worktree.py::resolve_mutation_owner` and `prove_terminal_retirement` | A sibling snapshot cannot authorize mutation. Retirement requires surviving terminal child records and review/provenance evidence. |
| `cascade/tracking.py::merge_request_snapshot` | GitHub requests the installed CLI's `commits` field and extracts the last OID as source revision. Missing/malformed commits cannot establish pinned source. Preserve other GitHub and GitLab snapshot fields. |

## Logic flow

```mermaid
sequenceDiagram
  participant Operator
  participant Feature as Feature repair
  participant Task as Task delivery
  participant Review as Review and forge
  participant Workspace as Workspace
  Operator->>Feature: request in-scope repair
  Feature->>Feature: inspect owner, generation, gates, heads and lease
  alt admitted
    Feature->>Task: retain identity; synchronize and validate moved heads
    Task->>Review: deliver current source/target pair
    Review->>Review: publish current or linked follow-up review
    Review->>Workspace: reconcile accepted heads and prove descendant survival
    Workspace-->>Operator: terminal board and postcheck evidence
  else stale or blocked
    Feature-->>Operator: typed refusal, owner and next action
  end
```

## Task breakdown

- `task_047_004_001` — End-to-end convergence matrix and final architecture reconciliation; no Task dependency.
- `task_047_004_002` — Installed GitHub CLI snapshot contract and reviewed runtime handoff; no Task dependency.

## Diagram-impact inventory

| Level and view | Owning design and source | Task acceptance |
|---|---|---|
| Landscape/context: `cascade-landscape`, `cascade-context` | Root `DESIGN.md`; `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}` | Check actor and external-system responsibilities; record a concrete no-change reason if unchanged. |
| Containers: `cascade-containers` | Root and `cascade/DESIGN.md` | Check supervisor, repository, forge and renderer boundaries; update only if the final diff changes communication or persistence. |
| Components: `cascade-supervisor-components`, `cascade-team-components` | `cascade/DESIGN.md` and affected child designs | Reconcile ownership and recovery collaboration, especially Feature, Boss, Watchdog, Task and Workspace. |
| Integrated Code: `cascade-feature-code`, `cascade-boss-code`, `cascade-watchdog-code`, `cascade-workspace-code`, `cascade-task-code`, `cascade-epic-code` | `cascade/{feature,boss,watchdog,workspace,task,epic}/DESIGN.md` and model source contract | Keep real source paths/symbols, declaration kinds, parent semantic IDs and relationships current; validate source, render and navigate Code from components. |
| Supplementary behavior | Same owning child designs, plus Board/War Room if their interfaces change | Explain normal, refusal, replay/restart, review publication and retirement; verify Level up, deep links and pinned source. |

Task 001 owns final diff reconciliation and UI/render evidence. Task 002 owns tracking/review/runtime documentation and any architecture edits its implementation changes. Both preserve accepted snapshots. No separate architecture-only Task is planned because that work is part of their delivery criteria.

## Risks & upward questions

None.

## Decision log

None yet.

- `dec_001` · 2026-11-24 · Feature Lead · **Task breakdown and diagram-impact inventory**
  Chose Use two independent Tasks: end-to-end convergence with final architecture verification, and installed-CLI plus reviewed-runtime handoff coverage..
  Rationale: The contracts exercise different boundaries and can run concurrently. The architecture/UI checks belong with the integrated scenario because they verify the same final source and preserve the feature's two-Task budget.
  Honors: epic_047 criteria 11 and 13–15; Feature scope and design-skill source-linked C4 verification..

## Closeout

Completed child work: `task_047_004_001` (Prove late repair lifecycle convergence and architecture closeout), `task_047_004_002` (Verify GitHub CLI snapshot contract and reviewed runtime handoff).
