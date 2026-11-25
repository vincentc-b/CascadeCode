---
id: task_047_002_003
title: Revalidate original Task delivery and publish the correct review
tier: task
status: completed
parent: feat_047_002
children: []
depends_on:
- task_047_002_002
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
# Revalidate original Task delivery and publish the correct review

## Parent Feature

[feat_047_002](../../features/2_active/feat_047_002_admit_late_repair_generations_without_losing_accepted_review_history.md); use pinned parent_rev and its Task/review contract.

## Depends on

- task_047_002_002

## Acceptance criteria

- Reuse the original Task ID, checkout, committed implementation, queued delivery action and prior validation/attempt history. Before rearm or merge compare both source and target heads with the recorded final-validation pair. A move of either head, including the Feature reactivation document commit, uses existing branch synchronization and supervised Task final validation; current evidence changes only after green tests. Refuse live execution owner, stale claim, dirty/protected/missing checkout and changed mutation owner without deleting work.
- Link the Task delivery action to the repair generation. A still-current validated pair resumes delivery without a new SWE implementation turn. A stale pair does not consume old green evidence or silently mark Task complete. Preserve every historical attempt and exact source/target evidence.
- For a fresh open review, refresh the same URL only when authoritative forge facts show it open against the intended target, and publish the repaired source head after validation through existing publication/rebase safeguards. For a merged historical review, retain its URL/source/target/merge heads and create a distinct linked follow-up review from the retained Feature branch to the owning Epic branch. Unknown or conflicting review facts fail closed. Never treat local Task merge, review acceptance, parent integration or runtime deployment as interchangeable.
- Reconciliation matches callbacks to their own immutable generation and checks exact accepted source/target heads plus independent integration before completing the current obligation. An old PR callback remains historical after follow-up exists. Retirement remains blocked until current review and integration obligations are proven.
- Test one normal current-pair delivery with open-review refresh and one moved-source/target refusal then green revalidation. Include merged-review follow-up and old-callback ordering; failure at validation replacement and review publication/save must resume without duplicate MR or accepted-head rewrite.
- Reconcile cascade/task/DESIGN.md, cascade/boss/DESIGN.md and cascade/DESIGN.md with real source-linked validation/publication flows, persistent evidence, failure and restart behavior. Update cascade-task-code and cascade-boss-code, and any Feature code node actually changed, with correct declaration kinds and source contract.

## Files likely touched

cascade/task/action_recovery.py, cascade/task_rollup.py, cascade/task/supervisor_recovery.py, cascade/workspace/branch_synchronization.py, cascade/boss/merge.py, cascade/review.py, cascade/feature/publication.py, cascade/task/DESIGN.md, cascade/boss/DESIGN.md, cascade/DESIGN.md, architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}, tests/task/, tests/boss/ and focused review tests.

## Implementation notes

Use current action/review-generation API from predecessor Tasks. Any external forge/test I/O runs outside lifecycle and review locks; recheck claim and heads on return. Preserve the existing reviewed publication/rebase and stacked-review mechanisms. Exact review evidence must be tied to the published source and target pair; a historical closed Boolean is insufficient.

## Skills

_(none; default SWE and design role playbooks apply)_

## Test plan

Production-boundary Task action/merge and review-poll integration tests for current versus moved heads, open versus merged review, old callback, failed final validation and publication replay. Run relevant task/boss/review tests, source-contract validation, supported local render for changed views and git diff --check. Trace normal and refusal/resume paths.

## Out of scope

New Task implementation, duplicate/reparented Task, automatic deployment, general forge adapter rewrite, parent/audit incident routing and unrelated review UI changes.
