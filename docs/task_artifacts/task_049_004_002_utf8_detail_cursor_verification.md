# UTF-8 detail cursor verification

## Integrated baseline and implementation

The scoped checkout baseline is `a5f3f6ef147e1aade7989de60e8d06b4bb090450`.
The existing implementation under review is
`cascade/war_room/transcript_pages.py::read_transcript_detail`. It validates the
cursor's graph, message, incarnation, digest and byte offset, opens only the
immutable projected detail blob with no-follow semantics, rejects an offset
whose first byte is a UTF-8 continuation byte, and returns an aligned chunk with
the next byte offset.

The loopback fixture is
`tests/war_room/test_transcript_pages_api.py::transcript_server`. The public
detail route exercised by the regression is
`GET /api/transcript/v1/epic_001/items/large-message/detail?cursor=<opaque>` via
`cascade/war_room/sidecar_routes.py::handle_get_transcript`.

`test_oversized_detail_reconstructs_utf8_and_rejects_foreign_or_stale_cursor`
uses an oversized emoji/CJK body and verifies:

- every incomplete successful response returns a distinct cursor whose byte
  offset advances exactly by the encoded chunk length;
- graph, message, incarnation and digest remain unchanged across continuations;
- chunks are at most 64 KiB, reconstruct the exact body, and terminate with
  `complete: true` and no next cursor;
- editing the opaque cursor one byte into the first emoji returns HTTP 400
  `invalid_request`;
- foreign graph/message identity is invalid, while changed digest or
  incarnation uses the existing HTTP 409 `cursor_restart` contract;
- detail GET does not open writer SQLite, scan JSONL, or mutate projection
  artifacts, and each response remains below 256 KiB.

The neighboring module fixtures retain the compatible chat completeness,
incarnation, continuation and `Link` header checks, typed pending/restart/error
checks, and the 1 MiB source budget exercised by transcript publication and
reads.

## Focused verification

Command:

```text
pytest -q tests/war_room/test_transcript_pages_api.py
```

Result on the uncommitted scoped diff: `9 passed in 48.11s`.

## Design and diagram-impact reconciliation

- Landscape/context (`cascade-landscape`, `cascade-context`): unchanged because
  the diff adds no actor, external system or responsibility boundary.
- Containers (`cascade-containers`): unchanged because the loopback route,
  Python runtime and immutable projection storage boundary are unchanged.
- Components (`cascade-war-room-components`): unchanged; the Dashboard still
  owns the transcript route and bounded projection reader.
- Code (`cascade-dashboard-code`): the existing `read_transcript_detail`
  Function node resolves to `cascade/war_room/transcript_pages.py`, and the
  existing route-to-reader relationship matches the call in
  `handle_get_transcript`. No symbol, declaration kind, ownership or wiring
  changed.
- Supplementary behavior: `REQ-WARROOM-TRANSCRIPT-005` and the War Room entry
  point table already state the current 64 KiB UTF-8-aligned detail behavior,
  invalid inside-character cursor rule, 1 MiB source cap and 256 KiB response
  cap. No design edit is needed.

The dependent integration task still owns browser evidence for context-to-Code,
Level up, deep-link restoration, pinned source navigation, warm reuse and render
bounds. This scoped API task does not alter the model or renderer and therefore
does not manufacture replacement browser evidence.
