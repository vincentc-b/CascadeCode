---
id: epic_054
title: Verify merge results and preserve canonical trunk integrity
tier: epic
status: active
parent: null
children:
- feat_054_001
- feat_054_002
- feat_054_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-25'
updated: '2026-11-27'
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
# Verify merge results and preserve canonical trunk integrity

## Intent

Make a review merge a verifiable delivery boundary rather than treating a clean PR or a green feature-branch check as proof that the integrated product is healthy. Epic 048 exposed three related facts: PR #256 was green on its reviewed Feature head, but the later Epic #259 merge into main encountered a Task boot contract already present on the target (3321179b), yielding two failing late-repair convergence tests; the merge also resurrected four stale backlog Feature records alongside their completed copies, making the War Room board unavailable in Epic 051's new checkout. The operator had to reconcile the merged main tree, remove only stale duplicate records, fast-forward the affected checkout, and synchronize local/remote main at 5c3cddc7. A subsequent corrective PR #260 was green while exact merged main failed a rapid equal-size Python edit/retest; PR #261 removed that fixture timing dependency, and exact main c0346bff passed 163 tests. Preserve the normal human review/merge authority, but ensure validation and board integrity are checked on the actual integration result, and keep post-merge recovery actionable without manual Git surgery.

### Success criteria

1. Bind each required review check to exact source and current target revisions, the prospective merge result/tree and the approved validation profile. For Feature-to-Epic and Epic-to-trunk review, validate the actual integration result rather than trusting source-only or an earlier green check. A target change invalidates stale evidence and triggers bounded revalidation without reopening unchanged work or duplicating reviews. Preserve task delivery validation and existing forge review protections; do not auto-merge or override human approvals.
2. Before publication/merge acceptance, independently scan the prospective physical board across all columns for malformed or duplicate IDs, stale moved records, parent/child identity and terminal history. Enforce one authoritative record per work ID in every publishable checkout. Reproduce Epic #259's stale backlog/completed duplicates and refuse the bad merge result before it can poison a new Epic worktree. Reuse the existing publication board validator, canonical owner resolution and guarded merge path; never silently choose a duplicate by column rank. Retain unrelated specifications and exact accepted cancellation feedback/history, even across divergent, split-root, squash/rebase and stacked review histories.
3. After an operator or forge merge, reconcile actual remote trunk commit and current local trunk, using a fresh remote observation. Fast-forward a clean eligible checkout automatically through the normal sync path; for divergence, dirty work or semantic conflict, retain changes, use a bounded supported reconciliation/preview path and identify actionable owner prerequisites. Never reset, overwrite, discard uncommitted work or force push. Report local/remote head identities, actual synchronization result and exact board availability. Ensure new integration checkouts cannot inherit a malformed or unverified trunk.
4. Observe required CI on the exact accepted merged revision. Distinguish prospective check green, actual merge, post-merge check pending/red/unknown, and independently verified closure. Route fixable post-merge failures to the accountable Epic/Feature or a supported corrective repair on the correct branch; preserve incident budgets, accepted review lineage and the current reviewed target. Coordinate with Epic 051's review ownership so no already-completed team is left with an unprocessable fix request. A failed check or missing evidence never becomes successful merely because a review merged. Preserve human release/approval policies and avoid repeated unchanged polling/model turns.
5. Validate from an isolated exact tested tree with reproducible declared dependencies and fresh effective source. Prevent stale generated artifacts, timestamp-based Python bytecode or other cache inputs from causing incorrect red/green evidence; do not modify product code merely to make a test fixture pass. Keep the original validation scope and bounded runtime, capture sanitized actionable diagnostics, and distinguish actual product failure from environment/fixture failure. Verify independently that the expected failed assertion really occurred in red-to-green regressions and that the corrected revision is the one validated.
6. Acceptance: use real temporary Git repositories/worktrees and production review/sync adapters with scripted forge transport where necessary. Reproduce all three Epic 048 cases: green Feature PR but changed-target boot contract causing a failed integrated gate; stale backlog Feature copy reintroduced by diverged merge, poisoning a newly activated Epic; same-second source edit and stale validator cache. Demonstrate pre-merge refusal or fresh exact merge-result check, verified repair, no duplicate IDs or history loss on final remote and local main, no unwanted checkout mutation, green exact merged-trunk CI, and correct reactivation/recovery ownership. Test target movement during checks, restart, offline forge, dirty/diverged main, split roots, duplicate delivery, stale review receipts and human-only gates. Check normal and failure paths through the War Room with explicit statuses and no mutations from UI polling.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Reuse cascade/review_validation.py, review_rebase.py, team_review_recovery.py, review.py, tracking.py, boss/epic_complete.py, workspace/integration_worktree.py, board/store.py, workspace/branch_synchronization.py and existing Watchdog action, validation and review evidence. Coordinate with Epic 051 (review-pending owner lifecycle), Epic 053 (superseded child/canonical cancellation), Epic 049 (visibility) and Epic 048 (durable budgets and verified recovery). This brief owns merge-result validation, canonical publishable board integrity and post-merge trunk convergence, not replacement lifecycle, a new forge service, a parallel scheduler or a second incident ledger. Preserve existing review protections and original budget/authority; filing this brief authorizes no deployment, force merge, destructive checkout change or implementation before normal approval. Update owned designs and affected architecture views only against actual code.

## Core dependencies

To be identified during epic planning.

## Feature breakdown
- feat_054_003
- feat_054_002
- feat_054_001

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-25 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
