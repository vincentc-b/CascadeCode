---
id: task_043_001_002
title: Expose manifest tools only to owning Epic planning roles
tier: task
status: completed
parent: feat_043_001
children: []
depends_on:
- task_043_001_001
owners:
- swe
skills: []
parent_rev: f281d4e334740f7d7195f13b4eedc22216b07c12
created: '2026-11-07'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose manifest tools only to owning Epic planning roles

## Parent Feature

[feat_043_001](../../features/2_active/feat_043_001.md)

## Depends on

- task_043_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Register `read_dependency_manifest` and `write_dependency_manifest` in the Epic planning registry and MCP/custom-tool catalogs for `epic_manager` and `epic_architect` only. Bind the trusted session role, Epic ID, and owning integration worktree at runtime, including direct dispatcher calls that bypass JSON schema validation. Deny feature/task/Boss callers, role/actor/root/Epic overrides, unknown fields, completed or non-owned Epic writes, symlink/path escapes, and trunk fallback. Keep these tools separate from the generic sidecar guard and from software installation/approval capabilities. Ensure any tool descriptions and schemas match the public request contract. Add focused runtime permission checks where needed.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.

## Final direct delivery · 2026-11-08

Status: completed. Implementation through `a37f05ff` and preceding commits supersedes the earlier partial-completion audit. The operator explicitly requested implementation directly on main because the affected tool could not reliably implement its own repairs. No acceptance criteria are waived.

This existing child plan is satisfied by the Epic 43 implementation delivered directly on main. Its scope, requirements and accepted history are preserved; completion records the operator-authorized direct delivery, not a fabricated Task merge or forge review. The Epic 43 final-delivery section maps the acceptance evidence.

Validation: the combined affected acceptance suite passed 164 tests; additional targeted crash, failure, and cross-process checks passed. This records scoped acceptance, not a claim that every unrelated repository test passes.
