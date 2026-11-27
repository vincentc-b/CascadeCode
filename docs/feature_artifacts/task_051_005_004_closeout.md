# Task 051.005.004 integrated architecture closeout

## Design and source reconciliation

Reviewed the integrated implementation through Tasks 051.005.001–003 from the
changed leaves in `cascade/watchdog/dispatch.py`, `cascade/stacked_dispatch.py`,
`cascade/boss/view.py`, `cascade/review.py`, `cascade/review_health.py`,
`cascade/task_rollup.py` and `cascade/war_room/serialize.py`. Reviewed the owning
`cascade/watchdog/DESIGN.md`, `cascade/task/DESIGN.md`,
`cascade/boss/DESIGN.md`, `cascade/feature/DESIGN.md` and `cascade/DESIGN.md`,
then checked the unchanged consumer and ownership boundaries in
`cascade/workspace/DESIGN.md`, `cascade/epic/DESIGN.md` and root `DESIGN.md`.

The package design owns the shared delivery projection and execution predicate.
Watchdog owns dispatch admission and review observation. Task owns durable queued
action metadata, evidence-generation evaluation and retry charging. Feature owns
its scoped retry adapter, while Boss owns candidate visibility. The designs link
these owners without duplicating their requirements or decisions. Added prose is
current-state architecture rather than delivery attribution or chronology.

The native model represents each new symbol once. All six added Code declarations
are Functions in source: `_dependency_review_pending`,
`feature_dispatch_blockers`, `feature_delivery_satisfies_integration`,
`cascade.boss.view._deps_met`, `retry_task`, and
`_dependent_feature_for_task`. Their `cascade.codeComponent`, `cascade.parent`,
`cascade.sourcePath` and `cascade.sourceSymbol` values agree across `model.dsl`,
`views.dsl` and `workspace.contract.json`. Contract validation and the real
renderer found no missing, renamed, deleted, stale, or multiply owned affected
node.

## Diagram-impact inventory

| View | Owner and source symbols | Reconciliation and verification |
|---|---|---|
| `cascade-context` | Root/package design; existing Operator, Cascade, forge, provider and Structurizr systems | No person, external dependency or responsibility boundary changed. Retained after final-diff review, 24-view render and browser traversal. |
| `cascade-containers` | `cascade/DESIGN.md`; existing Service, repository and forge boundaries | The change reuses the review registry, Task action ledger and Git evidence. It adds no runtime, store, process, network path or isolation claim. Retained and traversed in Chromium. |
| `cascade-supervisor-components` | Package plus Watchdog/Boss designs; delivery projection, dispatch and candidate gates | Existing Watchdog, Boss, Board and Task-team ownership remains. Relationship descriptions now name current Feature delivery evidence and integration-required dispatch. The full model rendered successfully. |
| `cascade-team-components` | Package, Task and Feature designs; `record_upstream_review_observation`, `retry_pending_task_merges`, `retry_task` | Existing Watchdog→Task observation and Feature→Task retry boundaries remain the single owners. Descriptions now state exact-route same-Epic dependency selection and canonical retry dispatch. |
| `cascade-watchdog-code` | `cascade/watchdog/DESIGN.md`; `_dependency_review_pending`, `feature_dispatch_blockers`, `dispatch_task`, `_route_actionable_review_health` | Added two Function nodes and relationships to the shared Boss-owned delivery predicate. Chromium reached the view from context and opened pinned `_dependency_review_pending` source. |
| `cascade-task-code` | `cascade/task/DESIGN.md`; `record_upstream_review_observation`, `_dependent_feature_for_task`, `retry_pending_task_merges`, `resume_action` | Added the dependency-proof Function node and relationship from the durable observation entry. The existing action-ledger node remains the persistence owner. Chromium opened pinned dependency-proof source. |
| `cascade-boss-code` | `cascade/boss/DESIGN.md` and package delivery contract; `feature_delivery_satisfies_integration`, `cascade.boss.view._deps_met`, `feature_delivery_view` | Added the shared predicate and Boss candidate-gate Function nodes, linked to the existing delivery projection. Chromium opened pinned predicate source. |
| `cascade-feature-code` | `cascade/feature/DESIGN.md`; `retry_task`, scoped registry and `dispatch_task` collaboration | Added the retry Function node and its registry/canonical-dispatch edges. Chromium opened pinned retry source. |
| `cascade-workspace-code` | `cascade/workspace/DESIGN.md`; queue delivery and retained Feature symbols | No Workspace source changed: graph wakeup, retained-owner selection, render scheduling, cache identity and bounded rendering are unchanged. The browser showed one render operation before and after warm navigation. |
| `cascade-epic-code` | `cascade/epic/DESIGN.md`; `recover_feature`, `request_feature_review_repair` | No Epic adapter or parent-authority source changed. Actionable review routing still joins the existing request adapter, so its current node and edges remain accurate. |

## Normal and failure/restart traces

Normal release starts with lifecycle dependency readiness. Watchdog and Boss read
one current bulk delivery projection and apply
`feature_delivery_satisfies_integration`. Exact current-generation acceptance on
the intended Epic target passes `_dependency_review_pending`; `dispatch_task`
then applies the existing approval, capacity, provider and lifecycle gates once.
The explicit stacked path remains separate: `feature_dispatch_blockers` may use a
supported predecessor branch without claiming Epic-target integration.

For a closed-unverified or unchanged-red restart, `reconcile_open_review_health`
passes the normalized blocker generation and exact source/target route to
`record_upstream_review_observation`. Task selects only queued Tasks whose direct
Feature owner declares that same-Epic dependency. On retry,
`_upstream_review_fence_waits` rechecks the route and ownership, records a new
evaluation without claiming the action, and waits. Equal evidence after restart
therefore spends no provider, validation, merge or recovery attempt. A material
generation change receives one ordinary evaluation; only independent verified
intended-target delivery releases the existing gated action. Unrelated Task
failure classification and attempt history remain with their normal owner.

## Verification and limitations

- `validate_c4_workspace` accepted 278 elements, 346 relationships and 24 views.
- The focused source-contract, real-render, delivery-consumer, queued-recovery and
  review-health run passed 48 tests in 101.36 s. The renderer produced the full
  pinned model, and its second submission reused the same artifact and binding
  manifest as a cache hit.
- Chromium 156.0.8078.4 against a commit-pinned local clone reached a ready full
  model in 62.505 s. It traversed context → containers → supervisor components →
  Code, used Level up, restored the Watchdog Code target from a deep link, and
  opened pinned Watchdog, Boss, Feature and Task source. Three warm deep-link
  reloads measured 1.699 s, 1.913 s and 2.296 s; durable render operations stayed
  `1 → 1`, demonstrating artifact reuse and no per-view renderer startup. These
  are measurements from this environment, not latency guarantees.
- Source declaration inspection and the renderer's source-binding checks agree
  that each added node is a Function at the recorded path and symbol.
- Accepted snapshots and historical render evidence were not changed. Final
  integrated publication remains with the Epic Architect.

No material design or navigation gap remains in the scoped diff. External forge
and provider behavior is exercised at the repository's scripted seams rather
than against live services; no deployment or live external action was performed.
