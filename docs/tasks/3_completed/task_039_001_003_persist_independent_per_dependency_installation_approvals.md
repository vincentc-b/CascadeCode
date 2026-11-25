---
id: task_039_001_003
title: Persist independent per-dependency installation approvals
tier: task
status: completed
parent: feat_039_001
children: []
depends_on:
- task_039_001_001
owners:
- swe
skills: []
parent_rev: 107699ab02abe6cdaadf5b5f75e94834a6ae4662
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist independent per-dependency installation approvals

## Parent Feature

[feat_039_001](../../features/2_active/feat_039_001.md)

## Depends on

- task_039_001_001

## Acceptance criteria

- Persist one immutable approval per dependency operation with human identity/time, reviewed entry snapshot/revision, and exact dependency ID, version, authoritative source, checksum/digest, target environment, scope/destination, operation, and cleanup plan. Unknown exact version, source, or integrity digest blocks approval.
- A batch interaction persists independent approval IDs and bindings. Changing any one bound field revokes current validity only for that entry; a whole-manifest revision or verification-only edit leaves unchanged approvals valid.
- A public operation-boundary guard fails closed on missing/stale approval or mismatched attempted operation, independently of provider sandbox and execution policy. Read-only discovery/checking remains callable without installation approval.
- Plan sign-off/approval and successful checks do not mint approvals. Attempts that represent setup can reference the matching approval ID.
- Integration/API tests exercise every binding field, batch independence, unchanged-entry survival, guard denial before a mutation callback under provider yolo and owned-worktree context, and approval-free read-only checks.

## Files likely touched

cascade/epic dependency approval module; authenticated Cascade MCP/API approval boundary as needed; tests/epic dependency approval integration tests.

## Implementation notes

Define and persist canonical, human-provenance approval records for each dependency installation/upgrade entry. Bind dependency ID, exact version, authoritative source, checksum/digest, target environment, install scope/destination, exact operation, cleanup plan, and reviewed entry snapshot/revision; include approver identity/time and attempt-to-approval reference contracts. Provide a public current-validity/operation-boundary check for slice B and fail closed for missing or changed fields, while leaving read-only checks free of installation approval. A batch creates independent records; unchanged entries survive whole-manifest revision changes; verification-recipe changes affect evidence separately. No installation runner or implicit approval from plan sign-off/approval. Cover every binding field, batch independence, and unchanged-entry survival with focused tests.

## Skills

_(none)_

## Test plan

Exercise durable approval reload and the public guard through the actual API boundary with a mutation spy. A single table-driven case may cover the eight binding fields.

## Out of scope

No installation or upgrade runner, automatic approval, blanket bootstrap authorization, or provider-specific permission bypass.
