---
id: task_027
title: propose_epic_amendment replaces feature stub
tier: task
status: completed
parent: feat_006
children: []
depends_on:
  - task_026
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# propose_epic_amendment replaces feature stub

## Parent Feature

[feat_006](../../features/3_completed/feat_006_amendment_protocol.md) — Amendment protocol.

## Depends on

- task_026 — Amendment record, sidecar writer, conflict lookup helpers

## Acceptance criteria

- `propose_epic_amendment(target_file, section, proposed_text, rationale, *, feature_id, root) -> amd_id` implemented in `cascade/feature/amendments.py` (not `stubs.py`):
  - Validates `target_file` resolves to the Feature's parent Epic path (read via scoped feature read / `read_doc` + parent check); **never writes** the Epic file.
  - If `find_open_for_section(epic_id, section)` returns a record in `pending` or `revise_pending`, raise a clear **conflict** error (feat_006 dec_004).
  - Sets Feature frontmatter `status: blocked` (file stays in `docs/features/2_active/`), commits via `feature_write_doc`.
  - Calls `cascade/amendments/store.write_sidecar` with Epic section baseline from Epic at Feature `parent_rev`.
  - Appends `AmendmentProposed` to **`docs/_queue/{epic_id}.jsonl`** via `append_event` with payload `{ feature_id, epic_id, section, diff_path, amd_id }` (dec_008).
  - Appends `Toast` to **`war_room`** queue with `kind: amendment`, human-readable body, link to diff or epic doc (feat_003 contract).
  - Returns `amd_id`.
- `mint_task` in `cascade/feature/mint.py` refuses when the Feature doc has `status: blocked` (distinct error message from blocking-comment refusal).
- Remove 501 implementation from `cascade/feature/stubs.py` for `propose_epic_amendment` (delete function or leave module comment-only); register tool from `cascade/feature/amendments.py` via `cascade/feature/wiring.py` `load_feature_tools()` import order.
- `tests/feature/test_amendments_propose.py` (new) covers: happy path sidecar + meta exist, feature status blocked, queue event on epic dest, war_room toast, conflict on second propose same section, no epic file mutation (git/path assertion), `mint_task` refused while blocked.
- Update or supersede `tests/feature/test_stubs.py`: stop asserting 501 for `propose_epic_amendment`; keep registry test pointing at real implementation (minimal change).

## Files likely touched

- `cascade/feature/amendments.py` (create)
- `cascade/feature/mint.py` (edit — blocked status gate)
- `cascade/feature/stubs.py` (edit — remove propose stub)
- `cascade/feature/wiring.py` (edit — import amendments module)
- `tests/feature/test_amendments_propose.py` (create)
- `tests/feature/test_stubs.py` (edit)

## Implementation notes

Reuse `cascade/amendments/store.py` only for sidecar I/O (dec_007). Do **not** implement `resolve_amendment`, `ack_amendment`, or Epic section apply. Do not add a feature-tool path that writes `docs/epics/2_active/epic_*.md`. Serialize proposals on the Epic graph operationally by conflict rule at propose time (dec_004), not by a client-side wait queue.

**Must NOT touch:** `cascade/epic/amendments.py`, `cascade/epic/stubs.py` (except no edits), `cascade/war_room/**`, `tests/epic/test_stubs.py`, `tests/war_room/**`, amendment store internals beyond public API (coordinate with task_026 types).

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/feature/test_amendments_propose.py tests/feature/test_stubs.py tests/feature/test_mint.py -q`

## Out of scope

- `resolve_amendment` / accept-reject-revise (task_028)
- `ack_amendment` (task_028)
- War Room pane wiring (task_029)
- Feature `record_decision` on reject (task_028)
