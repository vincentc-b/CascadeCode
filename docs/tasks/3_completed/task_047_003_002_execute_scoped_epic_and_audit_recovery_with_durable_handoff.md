---
id: task_047_003_002
title: Execute scoped Epic and audit recovery with durable handoff
tier: task
status: completed
parent: feat_047_003
children: []
depends_on:
- task_047_003_001
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
# Execute scoped Epic and audit recovery with durable handoff

## Parent Feature

feat_047_003. The Task frontmatter pins its parent revision. Honor epic_047 criteria 5–6 and 12, the exact mutation-owner contract and the existing generation-bound Feature repair action.

## Depends on

- task_047_003_001

## Acceptance criteria

1. Immediate Epic `recover_feature`/`supervise_child` verifies the direct Feature child and exact registered owner, then invokes the same canonical `feature_repair` inspect/admit/resume operation selected by Feature self-recovery for a completed-parent Task mismatch. It must not report a deduplicated TeamMessage or graph wakeup as an executed repair.
2. The audit capability registry names the owner, tier, `parent_lifecycle_mismatch` failure class, required evidence, durable store and finite retry policy. `dispatch_audit_recovery` performs fresh observation, exact-generation reservation, claim acceptance and only then the scoped executor. Simultaneous Feature/Epic/audit requests converge on one action and claim. A changed owner, status, pair or gate rejects stale admission.
3. Results separately show selected operation/owner, requested/admitted, acknowledged, executed, verified, refusal and next prerequisite. A live execution owner remains an expected wait. Missing/broken capability or persistent orchestration defect produces one generation-keyed scoped handoff under an eligible owner, or an exact operator prerequisite where no legal executor exists. Repeated unchanged investigation/sweeps do not duplicate messages, worker turns, publications or merge attempts; bounded reassessment remains available.
4. Preserve prior action attempts, validation pair, repair/review identities and all human approval, comment, dependency, forge, permission and lease gates. The adapter cannot fabricate a dispatch/repair authority event or edit another team's worktree.
5. Update `cascade/watchdog/DESIGN.md`, `cascade/epic/DESIGN.md` and `cascade/DESIGN.md` with current source-linked owner/call boundaries, persistence, normal/refusal/restart sequence and verification evidence. Update `cascade-watchdog-code` and `cascade-epic-code` native custom views plus `workspace.contract.json` for significant new symbols. Verify `cascade.codeComponent`, `cascade.parent`, `cascade.sourcePath`, `cascade.sourceSymbol` and declaration kind. Component edges must show the callable authority path; context and container topology stay unchanged because no external actor, store or deployable boundary is added.

## Files likely touched

`cascade/team_supervision.py`, `cascade/epic/recovery.py`, `cascade/feature/recovery.py`, `cascade/watchdog/{capabilities,audit_recovery,audit_investigation,reservations}.py`, focused `tests/epic/` and `tests/watchdog/`, owning designs and C4 source/contract.

## Implementation notes

Reuse the prerequisite Feature repair action and existing audit reservation/claim machinery. Keep bounded Git/forge observation outside the lifecycle lock and recheck owner/generation/gates inside it. Existing investigation outbox is a handoff, never authority. The audit worker must return a durable request/result contract that can later be postchecked. Handle split product/tracking roots and exact direct-child relationship. Do not make a second scheduler or ledger.

## Skills

_(none; default SWE and design playbooks apply)_

## Test plan

Run focused Epic supervision, watchdog capability/audit recovery and reservation tests. Include simultaneous callers, stale generation, live owner, missing capability, acknowledged-but-unexecuted request and restart/replay using production boundaries. Assert one action/claim and no duplicate side effects. Validate C4 source contract, real symbol links and `git diff --check`; record exact results.

## Out of scope

Final delivery/review/integration/persistence postcheck and broad UI/dashboard redesign; Task 3 owns shared projection and final verification.
