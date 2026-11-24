---
id: task_047_003_003
title: Verify recovery obligations and project one typed incident
tier: task
status: completed
parent: feat_047_003
children: []
depends_on:
- task_047_003_002
owners:
- swe
skills: []
parent_rev: f77efd3b2d94354dc620c6ff99f40324a5cf5e3d
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify recovery obligations and project one typed incident

## Parent Feature

feat_047_003. The Task frontmatter pins its parent revision. Honor epic_047 criteria 5–6 and 12, exact owner resolution, immutable repair/review generations, and the completed Task/delivery obligation.

## Depends on

- task_047_003_002

## Acceptance criteria

1. One authoritative postcheck for `parent_lifecycle_mismatch` re-reads the exact registered owner and canonical Task board/execution/delivery state, current Feature repair and review generation, accepted source/target heads, parent integration and descendant survival/retirement facts. It marks the associated repair incident verified only when all obligations owed by that generation are proven. Unknown legacy acceptance, a local status move, a queued message, a successful worker turn or an older merged review cannot clear it.
2. The shared typed incident links Task, parent and periodic-review projections with work/recovery identity, authoritative generation, failure reason, blocked operation/owner, original validation pair, prior and required review, selected capability/action, request/acknowledgement/execution evidence, freshness and verified outcome. Existing action/incident history remains available; resolved projections clear only after fresh postchecks, including after restart.
3. Keep audit producer and War Room GET bounded and read-only. Add only the fields needed for this incident to existing projection schemas/serializers; GET performs no Git, provider, forge or lifecycle probe and schedules no recovery. Missing/corrupt/stale projection data reports unknown or pending, never health.
4. Production-boundary integration evidence exercises one Task identity through Feature, immediate Epic and admitted audit requests; stale generation, live-owner wait, unavailable capability/handoff, acknowledged-but-unexecuted request, changed relevant facts, repeated sweeps and restart/replay. Assert one admitted repair, no repeated impossible merge/worker/message/review publication, preserved action history, and authoritative resolution. Preserve approval, dependency, comment, lease, ownership and review refusals. Leave broad open-versus-merged review and runtime deployment matrix for feat_047_004.
5. Reconcile `cascade/watchdog/DESIGN.md` owner of REQ-WATCHDOG-REPAIR-001 and `cascade/DESIGN.md` owner of REQ-CASCADE-RECOVERY-001 with implementation. Update Epic, Task, Feature and War Room designs only for local adapter/consumer implications. Describe current source-linked structure, action persistence, normal/failure/restart flow, interfaces and inspectable verification. Remove stale proposed claims; no delivery IDs or chronology in DESIGN.md.
6. Reconcile affected `cascade-watchdog-code`, `cascade-epic-code`, `cascade-feature-code`, `cascade-task-code` and component edges with actual significant functions/types. Update model and source contract together; validate declaration kinds, semantic ownership and source links. Verify context→container→component→Code Explore, Level up, deep-link restoration, representative pinned source, supported local render and warm artifact reuse. Record measured cold/warm evidence and any gap. Landscape/context and container views remain unchanged only if final diff adds no actor, external dependency, data store or runtime boundary; `cascade-teams-code` remains unchanged only if graph/provider wiring is unchanged.

## Files likely touched

`cascade/watchdog/{incidents,audit,audit_projection,audit_recovery,audit_investigation}.py`, `cascade/task/action_recovery.py`, minimal Board/War Room projection consumers, focused `tests/watchdog/`, `tests/war_room/` and production-boundary integration tests, owning designs, `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`.

## Implementation notes

Use existing projection/index page budgets and receipt epochs. Postcheck authority comes from canonical stores under the lifecycle boundary, not a cached UI snapshot. A required review may be open or accepted; verify the current generation at exact heads. The Feature/Boss/Workspace prerequisite code owns its own state and closeout; consume those contracts rather than duplicating state. Link all cross-design requirements to their single owner.

## Skills

_(none; default SWE and design playbooks apply)_

## Test plan

Run focused audit projection/reader, recovery and production-path integration tests. Use real canonical action/claim and board paths; deterministic forge transport may model review facts but may not synthesize lifecycle success. Validate C4 source contract and supported render, relative design/source links, navigation/pinned source, `git diff --check` and relevant publication safeguard command. Record commands, revisions, results and limitations in Task closeout.

## Out of scope

Audit dashboard redesign, a new renderer/service, accepted snapshot rewrite, full repository suite and runtime deployment.
