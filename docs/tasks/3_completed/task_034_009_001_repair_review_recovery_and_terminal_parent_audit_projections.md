---
id: task_034_009_001
title: Repair review-recovery and terminal-parent audit projections
tier: task
status: completed
parent: feat_034_009
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: d875650d1c0015a933aa88adb3fa3320b3826e12
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Repair review-recovery and terminal-parent audit projections

## Parent Feature

[feat_034_009](../../features/2_active/feat_034_009.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the approved feat_034_009 audit-projection repair in an isolated SWE task checkout. Reproduce persisted-store shaped F evidence: exact resolution action e58059ef admission mutation_ready; matching executions recovery_state=completed with completion_reconciliation.reason=review_health_restored; closed owner review and merged PR #218. Correct canonical reconciliation or read-only audit projection using exact action_id plus owning work/review identity and authoritative terminal completion. Retain history and idempotency. Closed review alone, unrelated/mismatched completion, unreadable evidence, and live/failed recovery must remain visible. Preserve main c0c1a891 review-identity and nested-handoff regressions. Also restrict stale-parent resume eligibility to nonterminal lifecycle states so completed/cancelled features with removed worktrees and later epic revision drift are not offered planning resume. Preserve active stale-parent recovery, cancelled-work cleanup, retained unpublished integration work, branch discrepancy, unresolved recovery, and unavailable evidence. Do not rewrite parent_rev, retry completed children, edit raw production state, reopen reviews, or delete receipts. Add focused integration/lifecycle regressions for both defects and countercases; run exact tests; publish canonical independent review. After accepted integration, request authoritative reassessment for F investigation_90d4c50f3e8326ebc96bc0186bbb96a5 and A–E investigations investigation_96ec034b51e42057d6b6b0e84cc87d8e, investigation_a217981361b70bd98a601b6e4ab27061, investigation_665e4c76e4fb559d37c2fe1ee780d142, investigation_835516b46bbe0b8eca73b4fedfa729c1, investigation_6269022dacd38e64a942fa2563e4c9d8. Feature H acceptance gaps remain separate.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
