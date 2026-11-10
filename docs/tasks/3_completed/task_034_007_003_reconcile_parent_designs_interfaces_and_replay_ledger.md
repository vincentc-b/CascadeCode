---
id: task_034_007_003
title: Reconcile parent designs, interfaces, and replay ledger
tier: task
status: completed
parent: feat_034_007
children: []
depends_on:
- task_034_007_002
owners:
- swe
skills: []
parent_rev: c57403e2106201d81c35a0c4cf7056f9ea5a23a3
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Reconcile parent designs, interfaces, and replay ledger

## Parent Feature

[feat_034_007](../../features/2_active/feat_034_007.md)

## Depends on

- task_034_007_002

## Acceptance criteria

- Reconcile verified leaf designs into parent and root DESIGN.md files, then check downward claims and cross-directory interfaces against current code/tests. Preserve one home for each requirement/decision ID, stable model IDs, and the mapping's single editing owner.
- Finish one replay-ledger row for every completed, non-cancelled eligible work item and every reachable target commit not covered by a work row. Each row names exact evidence revisions, review references when available, affected design paths and requirement/decision IDs, owner, and durable, superseded, no-impact, or unresolved disposition.
- Keep many-to-many work/commit/review links without double-counting shared evidence. Explicitly record unavailable review descriptions, ambiguous provenance, unreachable/deleted history, truncated replay, exclusions, and material unresolved coverage. Do not use cancelled plans as requirement sources; surviving code still requires Git/code inspection.
- Reconcile all accepted work and target commits added since Task 001's pin, including Feature F only if it has actually been accepted. Refresh the accepted baseline and preserve the original pin plus delta evidence.
- Stage ancestor and shared edits through their owning exact-revision review path. Record which revisions were accepted and which remain pending; do not claim closeout for unaccepted proposals.

## Files likely touched

- Configured architecture destination: parent/root DESIGN.md files, design mapping, model fragments and replay ledger/delta report.
- Focused ledger and coverage checks where needed.

## Implementation notes

Use the authorized Epic-owner handoff for sibling A–F work records; a completed-status projection is not their content. Check review descriptions via authorized forge access and mark unavailable sources explicitly. Ground current claims in code/tests rather than historical prose.

## Skills

_(none)_

## Test plan

Check ledger coverage against the pinned completed-work set and reachable commit set, including overlapping work/review/commit evidence and a direct fix. Check one-home IDs and representative parent/child and cross-directory claims against current implementation. Report missing authorized evidence and pending review gates.

## Out of scope

Final cross-feature acceptance and pinned DSL/JSON/SVG closeout belong to Task 004.
