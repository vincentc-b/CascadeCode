---
id: task_047_002_002
title: Gate child mint and closeout on current repair and review generation
tier: task
status: completed
parent: feat_047_002
children: []
depends_on:
- task_047_002_001
owners:
- swe
skills: []
parent_rev: adee5617fd3c69527f9b7d8ac199edca10c9f99c
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Gate child mint and closeout on current repair and review generation

## Parent Feature

[feat_047_002](../../features/2_active/feat_047_002_admit_late_repair_generations_without_losing_accepted_review_history.md); use pinned parent_rev and its mint, review and closeout contracts.

## Depends on

- task_047_002_001

## Acceptance criteria

- mint_task under an active parent retains ordinary behavior. Under a completed/open-review or accepted parent, require an admitted feature_repair action and legal owner/target route before a new nonterminal child becomes visible. Reserve the child ID and spec digest in the prepared action, then persist Task and parent child list idempotently. A crash/replay yields one Task identity and one generation. Keep comment, approval, dependency, owner, dirty/protected and live-lease refusals.
- Extend the existing Feature-keyed reviews.json entry with schema version, immutable generations and current_generation, while retaining top-level compatibility fields for readers. Each generation binds action, route, URL/forge ID, refs, observed heads, accepted merge SHA, publication action and reconciliation status. Historical merged facts remain immutable; legacy generation zero requires proven stored/live facts and unknown/inconsistent legacy acceptance refuses.
- Implement one current-obligation predicate for all rollup paths: all admitted Tasks terminal with exact delivery evidence; no prepared admission or live delivery; current review generation accepted at exact published heads; independent parent integration; current comments/approvals/dependencies and architecture gates. Put it before the already-completed fast path, under task_lifecycle_lock, and pass its result to feat_047_001's descendant-safe retirement proof. Review-disabled mode requires explicit local integration evidence.
- Serialize mint, closeout and retirement on the same fence. Test both race orders: closeout first makes later admission create a new obligation; admission first makes closeout defer. An old merged callback cannot close the newer generation or retire the checkout. Do not infer approval from completed status or a historical URL.
- Test normal late mint under an open review, and refusal for missing approval/unresolved blocking comment or an old callback. Fault-inject child-write and review-record save boundaries; verify replay does not duplicate a child or overwrite old acceptance.
- Reconcile cascade/feature/DESIGN.md, cascade/boss/DESIGN.md and cascade/DESIGN.md against current behavior with source-linked flow, persistent registry fields, failure/restart gates and one owner for REQ-FEATURE-REPAIR-001, REQ-BOSS-CLOSEOUT-001 and REQ-REVIEW-REPAIR-001. Update cascade-feature-code and cascade-boss-code with real symbols and source-contract declarations.

## Files likely touched

cascade/feature/mint.py, cascade/review.py, cascade/boss/rollup.py, cascade/workspace/integration_worktree.py (consumer only if needed), cascade/feature/DESIGN.md, cascade/boss/DESIGN.md, cascade/DESIGN.md, architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}, tests/feature/test_mint.py, tests/boss/test_rollup.py and focused review tests.

## Implementation notes

Use the action and authority API from task_047_002_001; do not write a separate admission gate. Review callbacks must carry their own generation identity. Keep review registry locks short and outside acquisition of the lifecycle lock; never hold a review lock while calling rollup. Existing publication/rebase and stacked-review obligations remain separate. Update only designs whose claims are reconciled to code; proposed symbols must not be described as implemented.

## Skills

_(none; default SWE and design role playbooks apply)_

## Test plan

Focused mint/rollup/review integration tests for active, open and accepted parent cases; both closeout race orders; blocking comments, approval/dependency and stale callback refusals; restart at child and review saves. Run affected suites, source-contract validation and git diff --check. Trace normal and refusal/resume paths.

## Out of scope

Actual Task branch synchronization/final validation and forge publication transport, parent/audit routing, UI redesign and broad review-registry migration unrelated to Feature repair.
