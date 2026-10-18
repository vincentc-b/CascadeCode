---
id: task_057
title: Plan markdown and Mermaid render
tier: task
status: completed
parent: feat_012
children: []
depends_on:
  - task_056
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# Plan markdown and Mermaid render

## Parent Feature

[feat_012](../../features/3_completed/feat_012_plan_viewer.md) — Plan viewer (View plan).

## Depends on

- [task_056](../../tasks/3_completed/task_056_plan_viewer_route.md) — plan route and HTML shell

## Acceptance criteria

- **`plan_viewer.js`** loads `GET /api/doc/{id}` and renders **`body`** into a dedicated `#plan-body` (or equivalent) container as HTML, not raw JSON.
- **Markdown** (client-side, no new Python dependency):
  - Vendored library under `cascade/war_room/static/vendor/` (e.g. `marked.min.js` or equivalent). **No CDN** at runtime.
  - Supports headings, paragraphs, lists, tables, blockquotes, inline code, and fenced code blocks with a language tag.
  - Unknown or unsafe HTML: use the library’s default sanitization or escape user HTML in code paths; do not execute script from plan bodies.
- **Mermaid**:
  - Vendored `mermaid.min.js` under `static/vendor/`.
  - Fenced blocks with info string `mermaid` are rendered as diagrams via `mermaid.run` (or the library’s documented init API) **after** markdown is in the DOM.
  - On Mermaid load failure, parse error, or timeout: replace or retain the block as `<pre><code>` with the source text; the rest of the page still renders.
- **Cross-doc links** (best effort): `<a href="...">` in the rendered body whose `href` is a relative path to another work markdown under `docs/` (e.g. `../../features/3_completed/feat_012_plan_viewer.md`) is rewritten to `/plan/{work_id}` when the filename prefix matches `epic_NNN`, `feat_NNN`, or `task_NNN`. External URLs and non-matching relative paths stay unchanged.
- **Optional meta line**: when `meta.parent_rev` is non-null, show a short pinned-SHA note in the header strip (no historical fetch).
- **Fixture test doc**: add a small epic/feature/task fixture under `tests/war_room/fixtures/` or use `tests/support.add_doc` with a body containing a ` ```mermaid ` block and a table; used by HTTP/JS tests.
- **Tests**:
  - `tests/war_room/test_plan_viewer.py`: extend with a doc whose body includes markdown + mermaid; assert HTML response shell still 200; assert static vendor files exist on disk (`mermaid.min.js`, markdown vendor).
  - `tests/war_room/test_plan_render.mjs` (new): Node subprocess (skip if `node` missing) that imports/exercises pure helpers exported from `plan_viewer.js` for: (1) mermaid fence detection, (2) work-id link rewrite for at least one relative href. Document `globalThis.PlanViewer` or `module.exports` pattern consistent with `board_focus.js`.
  - `tests/war_room/test_plan_render.py` runs the `.mjs` cases when Node is available.

## Files likely touched

- `cascade/war_room/static/plan_viewer.js`
- `cascade/war_room/static/plan_viewer.css`
- `cascade/war_room/static/vendor/marked.min.js` (or chosen markdown lib)
- `cascade/war_room/static/vendor/mermaid.min.js`
- `cascade/war_room/templates/plan_viewer.html` (script load order: vendor markdown → vendor mermaid → plan_viewer.js)
- `tests/war_room/test_plan_viewer.py`
- `tests/war_room/test_plan_render.py` (new)
- `tests/war_room/test_plan_render.mjs` (new)

## Implementation notes

Load scripts in dependency order in the template. Prefer extracting link-rewrite and fence-splitting into testable pure functions. Mermaid version: pin a single minified build in-repo; record version in a one-line comment at top of `plan_viewer.js` only if useful. Large bodies: synchronous render is acceptable for MVP. Do not add npm/webpack to the repo build — copy vendored files in-tree.

## Skills

_(none)_

## Test plan

```bash
pytest tests/war_room/test_plan_viewer.py tests/war_room/test_plan_render.py
```

## Out of scope

- **View plan** board control (task_058).
- Server-side markdown rendering in Python.
- Rendering `_amendments/` diff sidecars as plans.
- Syntax highlighting for non-mermaid code fences (plain `<pre>` is fine).

## Decision log

_(empty)_
