---
id: task_025
title: propose_epic_amendment 501 stub
tier: task
status: completed
parent: feat_005
children: []
depends_on:
  - task_018
  - task_019
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# propose_epic_amendment 501 stub

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

- task_018 — `register_feature_tool` registry
- task_019 — guard ensures no `_amendments` writes from this stub

## Acceptance criteria

- `FeatureToolUnavailable` (or shared unavailable type with `status_code = 501`) in `cascade/feature/stubs.py`.
- `propose_epic_amendment(target_file, section, proposed_text, rationale, *, feature_id, root)` raises 501 with message referencing **feat_006**; accepts parameters but validates nothing and writes **no** files under `docs/epics/2_active/_amendments/`, no diff sidecar format, no `AmendmentProposed` event.
- Tool registers via `register_feature_tool("propose_epic_amendment", ...)`.
- `invoke_tool` surfaces the 501 to callers consistently with epic stubs.
- `tests/feature/test_stubs.py` covers 501, no filesystem side effects, and registry presence.

## Files likely touched

- `cascade/feature/stubs.py`
- `tests/feature/test_stubs.py`

## Implementation notes

Do not set feature `status: blocked` on call — that behavior belongs to feat_006. Import from `load_feature_tools()` in task_024. Mirror `cascade/epic/stubs.py` `resolve_amendment` pattern.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/feature/test_stubs.py -q`

## Out of scope

- Amendment sidecar format, diff writer, `AmendmentProposed` / approve / reject (feat_006)
- Comment store (task_023)
- Epic `resolve_amendment` (remains 501 until feat_006)
