---
id: task_056
title: Plan viewer route and HTML shell
tier: task
status: completed
parent: feat_012
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# Plan viewer route and HTML shell

## Parent Feature

[feat_012](../../features/3_completed/feat_012_plan_viewer.md) — Plan viewer (View plan).

## Depends on

_(none — feat_003 is a feature dependency, not a task edge)_

## Acceptance criteria

- **`GET /plan/{id}`** on the existing War Room server (`cascade/war_room/server.py`):
  - Same loopback bind as the rest of the UI (`127.0.0.1` only).
  - `id` is a single work id (no `/`, no empty); unknown ids → **404** with the same JSON error shape as other War Room 404s when `Accept` is JSON, or a minimal HTML error page when the route is hit as navigation (implementation may always return HTML for this path).
  - Known ids → **200** `text/html; charset=utf-8` shell that includes: document title area (placeholder until JS loads), a **Back to War Room** link to `/` or `/war-room`, and script tags for `plan_viewer.js` (may be a no-op stub until task_057).
  - Embeds the work id in the page (e.g. `data-work-id` on `<body>` or a small inline config) so client code does not parse the URL twice inconsistently.
- **`cascade/war_room/views.py`** (or sibling module): `render_plan_page(work_id: str) -> str` using stdlib templating (same pattern as `render_war_room_page` — `string.Template` or manual escape); no Jinja.
- **Static files** (may be minimal in this task):
  - `cascade/war_room/static/plan_viewer.css` — readable typography for prose (headings, code, tables); full markdown styling can grow in task_057.
  - `cascade/war_room/static/plan_viewer.js` — at minimum fetches `GET /api/doc/{id}` and shows a loading state; rendering body HTML may be a `<pre>` escape of `body` until task_057 lands.
- **Header strip** (filled by JS from `meta`): show `id`, `title`, `tier`, `status`, repo-relative `path`, and `sha` (or “uncommitted” when null). Do **not** render YAML frontmatter as the article.
- **Tests** in `tests/war_room/test_plan_viewer.py`:
  - Loopback server fixture (same pattern as `test_http_read.py`).
  - `GET /plan/epic_001` → 200, `text/html`, contains `data-work-id` (or equivalent) and Back link.
  - `GET /plan/not_a_doc` → 404.
  - `GET /plan/epic_001/evil` → 404 (no path traversal).
  - Optional: `GET /static/plan_viewer.js` serves 200 when present.

## Files likely touched

- `cascade/war_room/server.py` (`do_GET` routing for `/plan/`)
- `cascade/war_room/views.py` (`render_plan_page`)
- `cascade/war_room/templates/plan_viewer.html` (new)
- `cascade/war_room/static/plan_viewer.css` (new)
- `cascade/war_room/static/plan_viewer.js` (new, stub OK)
- `tests/war_room/test_plan_viewer.py` (new)

## Implementation notes

Reuse `_handle_doc` validation rules for id shape. Prefer one template file over inline HTML in the handler. Escape all dynamic text with `html.escape`. Keep `/api/doc/{id}` unchanged. This task may ship before vendored markdown/Mermaid; the shell must not 500 when `body` is large.

## Skills

_(none)_

## Test plan

```bash
pytest tests/war_room/test_plan_viewer.py tests/war_room/test_http_read.py
```

## Out of scope

- Markdown-to-HTML and Mermaid (task_057).
- **View plan** board button (task_058).
- Editing plans or new write APIs.
- Fetching parent doc bodies at `parent_rev`.

## Decision log

_(empty)_
