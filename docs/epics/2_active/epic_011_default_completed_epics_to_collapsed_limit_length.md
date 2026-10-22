---
id: epic_011
title: default "completed" epics to collapsed, limit length
tier: epic
status: active
parent: null
children:
- feat_011_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-22'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Default completed epics to collapsed, limit length

## Intent

As completed work accumulates, keep the War Room focused on current work without making older epic history inaccessible.

The completed-epics section will start collapsed, display only the newest configured number of completed epics when expanded, and retain a repository link for browsing the full completed-epic history.

## Success criteria

1. The completed-epics section is collapsed on initial render.
2. The board displays at most **N** completed epics, where **N** is configurable in the project's Cascade YAML and defaults to **10**.
3. The retained entries are the newest completed epics according to the board's existing completed-epic ordering.
4. Missing, malformed, or non-positive limit values safely fall back to 10.
5. A visible link remains available to the repository location containing all completed epic documents.
6. Existing active and proposed epic sections are unchanged.

## Macro-architecture

Use the existing project-configuration path to expose one completed-epic display-limit value to the War Room. Keep the board's current completed-epic query and ordering as the source of truth, then apply the display limit at the board/view-model boundary before rendering. The completed section owns its initial collapsed presentation. Build the history link from the project's existing repository metadata and completed-epic path conventions rather than introducing a second archive or API.

Data flow:

`project Cascade YAML → validated limit (default 10) → existing ordered completed epics → bounded board model → collapsed UI section + repository history link`

## Cross-module constraints

- Preserve the current definition and ordering of “completed”; this epic only bounds presentation.
- Apply the limit after ordering so truncation cannot retain arbitrary or oldest entries.
- Configuration must be backward compatible: projects without the new setting continue to load.
- Treat malformed and non-positive values as absent and use the default of 10.
- Reuse existing repository URL/path construction and completed-doc location; do not hard-code a hosting provider or duplicate repository coordinates.
- The history link must remain visible even when the configured/default bound yields no rendered completed rows.
- Do not persist expanded/collapsed state as part of this epic.
- Avoid a new backend endpoint, pagination system, or archive store.
- Testing should concentrate on the board/render boundary: default collapse, default and configured bounds, retained ordering, invalid-value fallback, and link presence. Add lower-level tests only where behavior is not covered by that integration path.

## Core dependencies

- Existing project Cascade YAML loading and validation.
- Existing completed-epic collection and ordering used by the War Room.
- Existing collapsible-section UI behavior.
- Existing repository metadata and completed-epic document path/URL construction.

No new external service or package is expected.

## Feature breakdown

1. **feat_011_001 — Bound and collapse completed epics board**
   - Add the backward-compatible configurable limit with default/fallback 10.
   - Bound the already ordered completed-epic collection.
   - Default the completed section to collapsed.
   - Render the repository history link.
   - Add focused integration/render coverage for the complete behavior.

This is intentionally one feature: none of the individual changes is a useful independently shipped slice, and a single implementation path minimizes coordination and regression risk.

## Explicitly out of scope

- Pagination, search, or filtering for completed epics.
- Changes to active or proposed epic lists.
- Per-user persistence of expansion state.
- A new completed-work API, index, or duplicate archive.
- Repository-host-specific browsing features.

## Open questions

- The exact YAML key and UI component names should follow established conventions discovered during implementation; they do not alter the product contract above.
- If repository metadata is unavailable, preserve the board and omit or disable the history link using the application's established unavailable-link behavior rather than failing the page.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-10-22 · Epic Manager · Default the completed-epic display limit to 10 and fall back to 10 for missing, malformed, or non-positive configuration.
- 2026-10-22 · Epic Manager · Deliver the complete behavior as one feature; exclude pagination, preference persistence, and new archive infrastructure.
- 2026-10-22 · Epic Manager · Reuse existing completed ordering and repository metadata/path conventions, applying the bound only at the board presentation boundary.

- `dec_001` · 2026-10-22 · Epic Manager · **Configuration default and fallback**
  Chose Use 10 as the completed-epic display limit when configuration is absent, malformed, or non-positive..
  Rationale: Ten matches the approved brief, keeps the board compact, and gives legacy projects deterministic backward-compatible behavior.
  Honors: Success criteria requiring a configurable N and the requested last-10 default..
## Amendment log

_(none)_
