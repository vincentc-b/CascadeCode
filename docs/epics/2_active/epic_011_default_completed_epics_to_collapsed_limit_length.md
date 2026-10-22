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

The completed-epics section will start collapsed, display only the newest configured number of completed epics when expanded, and provide a repository link for browsing the full completed-epic history when repository metadata identifies a valid target.

## Success criteria

1. The completed-epics section is collapsed on initial render.
2. The board displays at most **N** completed epics, where **N** is configurable in the project's Cascade YAML and defaults to **10**.
3. The retained entries are the newest completed epics according to the board's existing completed-epic ordering.
4. Missing, malformed, or non-positive limit values safely fall back to 10.
5. When repository metadata identifies the completed-epic history location, a visible link is available to it; when that location cannot be determined, the completed section may remain empty.
6. Existing active and proposed epic sections are unchanged.

## Macro-architecture

Use the existing project-configuration path to expose one completed-epic display-limit value to the War Room. Keep the board's current completed-epic query and ordering as the source of truth, then apply the display limit at the board/view-model boundary before rendering. The completed section owns its initial collapsed presentation. Build the history link from the project's existing repository metadata and completed-epic path conventions when those inputs identify a valid target, rather than introducing a second archive or API.

Data flow:

`project Cascade YAML → validated limit (default 10) → existing ordered completed epics → bounded board model → collapsed UI section + repository history link`

## Cross-module constraints

- Preserve the current definition and ordering of “completed”; this epic only bounds presentation.
- Apply the limit after ordering so truncation cannot retain arbitrary or oldest entries.
- Configuration must be backward compatible: projects without the new setting continue to load.
- Treat malformed and non-positive values as absent and use the default of 10.
- Reuse existing repository URL/path construction and completed-doc location; do not hard-code a hosting provider or duplicate repository coordinates.
- When repository metadata identifies a valid history target, keep the history link visible even when the configured/default bound yields no rendered completed rows.
- When repository metadata cannot determine a history target, the completed section may render empty; do not fabricate a URL or disabled affordance.
- Do not persist expanded/collapsed state as part of this epic.
- Avoid a new backend endpoint, pagination system, or archive store.
- Testing should concentrate on the board/render boundary: default collapse, default and configured bounds, retained ordering, invalid-value fallback, link presence when metadata is available, and an empty completed section when history metadata is unavailable. Add lower-level tests only where behavior is not covered by that integration path.

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
   - Render the repository history link when repository metadata identifies its target, otherwise allow the completed section to remain empty.
   - Add focused integration/render coverage for the complete behavior.

This is intentionally one feature: none of the individual changes is a useful independently shipped slice, and a single implementation path minimizes coordination and regression risk.

## Explicitly out of scope

- Pagination, search, or filtering for completed epics.
- Changes to active or proposed epic lists.
- Per-user persistence of expansion state.
- A new completed-work API, index, or duplicate archive.
- Repository-host-specific browsing features.

## Open questions

_(none)_

## Implementation notes

- The exact YAML key and UI component names should follow established conventions discovered during implementation; they do not alter the product contract above.
- If repository metadata cannot determine the completed-history location, preserve the board and allow the completed section to render empty rather than fabricating a URL or disabled history-link affordance.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-22 · Epic Manager · **Configuration default and fallback**
  Chose Use 10 as the completed-epic display limit when configuration is absent, malformed, or non-positive..
  Rationale: Ten matches the approved brief, keeps the board compact, and gives legacy projects deterministic backward-compatible behavior.
  Honors: Success criteria requiring a configurable N and the requested last-10 default..

- `dec_002` · 2026-10-22 · Epic Manager · **Feature slicing**
  Chose Ship collapse, bounding, configuration, history link, and focused coverage as one feature (feat_011_001)..
  Rationale: These changes form one user-visible board contract and have no useful independently shippable subset; one slice reduces coordination and testing overhead.
  Honors: Ruthless prioritization and the smallest shippable slice..

- `dec_003` · 2026-10-22 · Epic Manager · **Implementation boundary**
  Chose Preserve existing completed-epic ordering and repository metadata/path conventions; apply the limit only at the board/view-model boundary..
  Rationale: This avoids changing domain semantics, adding storage, or hard-coding a repository host while ensuring the newest items are retained.
  Honors: The approved requirement to show recent completed work and link to full repository history..

- `dec_004` · 2026-10-22 · Epic Architect · **History-link degradation**
  Chose When repository metadata is unavailable, keep the history-link affordance visible but disabled using the application's established unavailable-link behavior..
  Rationale: This preserves page availability while keeping the epic's visible-link contract internally consistent and avoiding fabricated or host-specific URLs.
  Honors: Success criterion 5, the cross-module link-visibility constraint, and the existing repository metadata boundary..
## Amendment log

_(none)_
