---
id: task_026
title: Amendment record and sidecar diff store
tier: task
status: completed
parent: feat_006
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# Amendment record and sidecar diff store

## Parent Feature

[feat_006](../../features/3_completed/feat_006_amendment_protocol.md) — Amendment protocol.

## Depends on

None.

## Acceptance criteria

- New package `cascade/amendments/` exposes:
  - `Amendment` dataclass (or typed record) matching feat_006: `id`, `feature_id`, `epic_id`, `section`, `diff_path`, `proposed_text`, `rationale`, `state` (`pending` | `accepted` | `rejected` | `revise_pending`), `created` (timezone-aware datetime), optional `revised_text`, optional `reject_reason`.
  - `allocate_amd_id(root) -> str` monotonic `amd_NNN` by scanning `docs/epics/2_active/_amendments/*.meta.json`.
  - `section_slug(section) -> str` via `cascade.board.paths.slugify` (or re-export) for `{feature_id}_{section_slug}` basename.
  - `write_sidecar(amendment, epic_body_at_rev, *, root) -> Amendment` writes `.diff.md` (unified diff only) and `.meta.json` under `docs/epics/2_active/_amendments/` per feat_006 dec_002–dec_003.
  - `read_amendment(amd_id, *, root) -> Amendment` and `load_by_path(diff_path, *, root) -> Amendment`.
  - `update_amendment(record, *, root) -> Amendment` for state transitions (used later by task_027/028; implement persistence round-trip now).
  - `list_pending_for_epic(epic_id, *, root) -> list[Amendment]` where state is `pending` or `revise_pending`.
  - `find_open_for_section(epic_id, section, *, root) -> Amendment | None` for conflict detection (task_027).
- Unified diff generation compares Epic markdown **section body** (heading `## {section}`) at a supplied baseline text snapshot; tests use small fixture epic bodies.
- `tests/amendments/test_store.py` covers id allocation, write/read round-trip, slug paths, list/find helpers, and invalid/missing id errors.
- `tests/amendments/test_not_work_objects.py` (or combined file) asserts `list_board` does not surface `_amendments` paths as work docs and documents that watchdog `_active_markdown` glob does not descend into `_amendments/` (behavioral assertion via path layout, no watchdog refactor required unless a regression is found).
- **No** `propose_epic_amendment`, **no** `resolve_amendment`, **no** queue events, **no** feature status changes in this task.

## Files likely touched

- `cascade/amendments/__init__.py` (create)
- `cascade/amendments/types.py` (create)
- `cascade/amendments/diff.py` (create)
- `cascade/amendments/store.py` (create)
- `tests/amendments/test_store.py` (create)
- `tests/amendments/test_not_work_objects.py` (create, optional merge with above)

## Implementation notes

Follow feat_006 decision log dec_001–dec_003 and dec_009. Sidecar writes use direct filesystem I/O under `docs/epics/2_active/_amendments/`; they are **not** routed through `feature_write_doc` or `tool_guard` (feat_006 dec_007 — only the dedicated store module touches these paths). Do not add `_amendments` to board column scanners. Use existing `resolve_root` from board context where other modules do.

**Must NOT touch:** `cascade/feature/stubs.py`, `cascade/feature/amendments.py`, `cascade/feature/mint.py`, `cascade/feature/wiring.py`, `cascade/epic/stubs.py`, `cascade/epic/amendments.py`, `cascade/war_room/**`, `tests/feature/test_stubs.py`, `tests/epic/test_stubs.py`.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/amendments/ -q`

## Out of scope

- `propose_epic_amendment` / `resolve_amendment` / `ack_amendment` (task_027, task_028)
- War Room UI (task_029)
- Epic amendment log append on accept (task_028)
- Changing feature or epic tool guards beyond documenting store bypass (task_027 may reference this module)
