# War Room design

Purpose: expose the loopback operator UI/API for status, approvals, chat attachment, review, recovery, and diagnostics. Interfaces are `serve`, route modules, serializers/views, authenticated human actions, and static/template assets covered by this owner. Owns `REQ-WARROOM-001` (operator actions are explicit) and `DEC-WARROOM-001` (the UI projects canonical services rather than owning state).

Evidence: `cascade/war_room/` and `tests/war_room/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: forge descriptions unavailable in Task 001 remain explicit gaps.

## Refresh latency and coherent read projections

`REQ-WARROOM-REFRESH-001`: first board rendering must not wait for independent
flight, boss, chat, audit or provider panels. The board and pending-brief
cancellation lookup run concurrently, but both must finish before board actions
are enabled; cancellation safety is not traded for responsiveness. Optional panel
requests no longer delay startup polling. Existing forced post-action freshness and
single-flight board reads remain intact.

`DEC-WARROOM-REFRESH-001`: serialize Epic readiness from the same request-scoped
board snapshot used for the rest of the response. `project_epic_plan_readiness`
is explicitly a read projection; it does not refresh all registered worktrees per
Epic. `compute_epic_plan_readiness` and approval/sign-off/dispatch boundaries still
fetch authoritative dependency evidence independently of a supplied or cached board.
A UI snapshot is never permission to execute a lifecycle action.

Cold scans parse thousands of frontmatter records across retained worktrees. The
board parser prefers PyYAML's `CSafeLoader` when libyaml is available and falls back
to `SafeLoader`; both retain safe-constructor semantics, schema validation, dates,
round-trip behavior and rejection of Python object tags. This is parser acceleration,
not an additional stale-state cache or a relaxation of document validation.

Regression evidence: `tests/epic/test_plan_readiness.py` verifies no per-Epic fresh
scan in board serialization while authorization still refreshes; board parser
compatibility and unsafe-tag rejection are covered in `tests/board/test_parse.py`.
The refresh race harness covers cancellation lookup, optional-panel independence,
and forced post-action reads.

Board serialization also batches completed-Epic staging checks into one integration
registry snapshot, and shares one durable recovery-action snapshot between incident
and task-delivery projections. These snapshots live only for that response; the next
request rereads the registries, and existing locks and standalone action-boundary
reads remain unchanged. `tests/war_room/test_projection_batching.py` verifies the
read count, empty snapshots, and refresh across requests.

## Planned feature activation explanations and new-work attention

Epic `epic_045` specifies two successive slices, `feat_045_001` and
`feat_045_002`. This section records the reviewed design; implementation and its
acceptance evidence remain with those features. Epic success criteria 1–5 and
decision `dec_002` govern activation explanations; criteria 6–16 and `dec_003`
govern durable attention. Decision `dec_001` sequences the two slices.

Activation explanations extend the existing Python readiness projection while
preserving `approved` and `blockers` consumers. Canonical dispatch predicates
retain blocking sibling identities and distinguish execution from merge/review.
The board receives a versioned summary, all reasons, satisfied prerequisites,
owners, existing actions, observation freshness and optional actual dispatch
attempt evidence. A fresh human-action blocker takes precedence, followed by
unknown required evidence, known work/system waits, and fully evaluated readiness
awaiting dispatch. Passing gates never claims execution. Historical refusals stay
separate from a newer evaluation. Revision approval, dependencies, parent state,
review threads, provider inventory and dispatch-base facts retain their current
owners; feature planning must pin each source and its invalidation policy.

Acquire reusable facts once per board response. Missing cached evidence remains
unknown; polling must not introduce provider discovery, expensive per-feature Git
probes, dispatch, or lifecycle mutation. Actual actions re-evaluate their gates.
The browser renders reasons and actions without implementing eligibility rules.

Attention uses a separate versioned ledger keyed by canonical tracking workspace
and stable feature ID. Mint/startup reconciliation records creation or durable
first discovery; rendering never acknowledges. Workspace-shared Mark seen uses
the existing request-scoped human verifier and records actor/time. It is idempotent
and does not approve, dispatch, edit plans, or clear blockers. Resolve one shared
tracking-owned store across managed worktrees and split repositories, with atomic
persistence and cross-process locking. A monotonic state revision prevents an old
poll response from undoing an acknowledged marker in the UI.

First rollout atomically records known identities and exposes only open
backlog/ready-to-plan children of active, non-cancelling epics as unseen. Historical
identities are baselined; later additions remain unseen until explicit Mark seen.
Completed, cancelled and retired children leave pending-attention aggregates
without deleting provenance. Replay, plan edits and status/path changes cannot
recreate acknowledged newness. Unavailable or corrupt state must remain visibly
unavailable, never silently reset the baseline. Feature 002 must pin bootstrap,
concurrent mint and crash-recovery behavior before coding.

New text and collapsed-epic counts remain separate from lifecycle and activation
summaries, with keyboard navigation, readable contrast and screen-reader labels.
Focused API/integration coverage owns state and gate invariants; a browser journey
proves discovery of two corrective features, explicit acknowledgement and refresh
persistence. Neither slice changes scheduling or human approval policy.

Architecture impact: **no diagram change**. These additions stay inside the
existing War Room, supervisor/team readiness and workspace/repository persistence
boundaries represented by `element.container.war-room`,
`element.container.supervisor` and `element.container.repository`. They add no
deployment unit, external service, actor, or C4 relationship. The existing
`cascade-containers` and `cascade-supervisor-components` views retain their meaning;
the ledger schema and explanation fields belong in the child feature contracts.

Planning validation (2026-11-12): the four reconstructed-design checks passed.
The three existing board-feature-readiness cases failed during fixture setup:
`approve_board_feature` attempts approval while a declared dependency is still
backlog, and the current action boundary correctly raises `dependency_unmet`.
Feature 001 must update those fixtures to establish approval through a legitimate
dependency-satisfied state before exercising later waiting states; these cases are
not passing baseline evidence. No product code changed in this review.
