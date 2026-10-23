---
id: task_016_002_001
title: Expose branch drift and safe update API
tier: task
status: completed
parent: feat_016_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: db13b2bf583ea4144dfacab302980a6287b064ab
created: '2026-10-23'
updated: '2026-10-23'
---
# Expose branch drift and safe update API

## Parent Feature

[feat_016_002](../../features/2_active/feat_016_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Extend the active board read model and add the update-branch endpoint using the synchronization service delivered by feat_016_001.

## Scope

- Serialize resolved base, ahead/behind counts, update eligibility, and a stable disabled reason for active epics, features, and tasks.
- Add one POST endpoint that validates the work ID and delegates Git policy to the shared synchronization service.
- Return a stable JSON result with appropriate success, client, and conflict statuses.
- Map dirty_index, local_changes, branch_conflict, busy, and invariant failures to concise actionable payloads.
- Include only validated conflict paths and confirmation that an attempted merge was aborted; never expose raw Git output.
- Reuse the same actionable failure vocabulary for existing task-merge and epic-close failures while preserving their retry semantics.
- Keep remote fetch, automatic retries, stashing, conflict resolution, and lifecycle changes out of scope.

## Verification

Add focused route/serialization coverage for epic, feature, and task tiers, success/current transitions, domain preconditions, status mappings, safe conflict paths, and redaction of raw Git output.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
