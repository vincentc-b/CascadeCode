---
id: task_046_003_001
title: Resolve known branch contexts and exact documentation refs
tier: task
status: completed
parent: feat_046_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 179c609e5907e205b01fe1e1157dc2f908570b5d
created: '2026-11-11'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resolve known branch contexts and exact documentation refs

## Parent Feature

[feat_046_003](../../features/2_active/feat_046_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Expose only the War Room session target and registered project contexts as selectable repository/worktree identities. Default to the session target; resolve each selected code ref to a full commit and accurately label branch, detached HEAD and dirty status. Resolve the configured architecture destination and stable mapping at pinned revisions. For split repositories, use only exact recorded code-to-document association from review, promotion or lineage evidence; distinguish accepted lineage. If no unique association exists, return documentation_ref_required with selectable known documentation refs and record an explicit user-selected ref, never tracking HEAD. Keep the resolver scoped to known contexts and prepare the selection/provenance seam for feat_046_004. Focused tests cover default, second branch, detached, dirty, split associated/ambiguous/missing refs and forbidden arbitrary paths.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
