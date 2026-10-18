---
id: task_028
title: resolve_amendment and ack_amendment replace epic stub
tier: task
status: completed
parent: feat_006
children: []
depends_on:
  - task_026
  - task_027
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# resolve_amendment and ack_amendment replace epic stub

## Parent Feature

[feat_006](../../features/3_completed/feat_006_amendment_protocol.md) — Amendment protocol.

## Depends on

- task_026 — Amendment store read/update
- task_027 — Real proposals, blocked feature state, queue events

## Acceptance criteria

- `resolve_amendment(amd_id, decision, note=None, revised_text=None, *, epic_id, root) -> str | None` in `cascade/epic/amendments.py`:
  - **`accept`:** Replace Epic `## {section}` body with approved text (from record: `revised_text` if revise flow completed, else `proposed_text`); commit via `epic_write_doc` / board git helpers; append **Amendment log** entry on Epic body (new helper in `cascade/amendments/` or `cascade/epic/amendments.py` mirroring decision-log append style); optional `record_decision` when architect locks choice; set amendment `state=accepted`; enqueue `AmendmentApproved { feature_id, epic_id, epic_rev }` to **feature** queue; update Feature doc `parent_rev=epic_rev`, `status=active`; return SHA string.
  - **`reject`:** Epic file unchanged; `state=rejected`; enqueue `AmendmentRejected { feature_id, epic_id, reason }` (reason from `note` or default); set Feature `status=active`; call Feature-side decision append (via `cascade/feature/decisions.py` or shared helper) documenting dec_005 — minted Tasks not auto-validated for dispatch; return `None`.
  - **`revise`:** Require `revised_text`; set `state=revise_pending`, persist `revised_text`; Feature stays `status=blocked`; return `None`. No Epic mutation.
  - Invalid `amd_id`, wrong `epic_id`, or wrong state transitions fail closed with clear errors.
  - No auto-accept; Feature cannot leave `blocked` except via accept, reject, or full revise+ack+accept/reject path (dec_006).
- `ack_amendment(amd_id, *, feature_id, root) -> None` in `cascade/feature/amendments.py`:
  - Allowed only when record `feature_id` matches, `state=revise_pending`.
  - On success: update record to `pending`, set `proposed_text` to acknowledged `revised_text` (per dec_006), regenerate or update `.diff.md` via store helper; Feature **remains** `status=blocked` until Epic `resolve_amendment` accept/reject.
- Remove 501 `resolve_amendment` from `cascade/epic/stubs.py`; register from `cascade/epic/amendments.py` in `cascade/epic/wiring.py`.
- `tests/epic/test_amendments_resolve.py` covers accept (epic commit SHA, amendment log line, queue event, feature parent_rev), reject (epic unchanged, feature active, AmendmentRejected), revise + ack state machine, return type SHA vs None.
- Update `tests/epic/test_stubs.py` to stop asserting 501 for `resolve_amendment`.
- `tests/feature/test_amendments_ack.py` covers ack preconditions and blocked-until-resolve behavior.

## Files likely touched

- `cascade/epic/amendments.py` (create)
- `cascade/feature/amendments.py` (edit — add `ack_amendment`)
- `cascade/amendments/log.py` or extend `store.py` (create/edit — epic amendment log append only if owned here)
- `cascade/amendments/section.py` (create, optional — Epic section replace helper)
- `cascade/epic/stubs.py` (edit — remove resolve stub)
- `cascade/epic/wiring.py` (edit)
- `cascade/feature/wiring.py` (edit — register ack if separate register call)
- `tests/epic/test_amendments_resolve.py` (create)
- `tests/feature/test_amendments_ack.py` (create)
- `tests/epic/test_stubs.py` (edit)

## Implementation notes

Use `cascade.board.gitutil` / `epic_write_doc` for accept commits (DESIGN §9.2). Epic queue consumption is not required in this task — War Room calls tools directly (task_029). On accept, Feature re-read is modeled by updating `parent_rev` and status only; graph reload is existing boot/read behavior. Reject decision-log text must explicitly mention task dispatch / stale task specs (dec_005).

**Must NOT touch:** `cascade/war_room/**`, `tests/war_room/**`, `cascade/feature/mint.py` except if a shared constant is needed (prefer not), `task_027` propose tests except shared fixtures.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/epic/test_amendments_resolve.py tests/feature/test_amendments_ack.py tests/epic/test_stubs.py -q`

## Out of scope

- War Room HTTP/UI (task_029)
- Changing `propose_epic_amendment` behavior (task_027)
- Watchdog reactions beyond existing queue append
