# task_046_005_001 — live paired C4 acceptance

The authoritative acceptance is
`tests/war_room/test_architecture_planning_browser_journey.py`. It creates a
new Git project, mints its feature through the registered Epic planning tool,
commits and accepts an initial C4 model, and publishes a second proposal through
the registered Feature planning tool. After creating semantic threads, it
publishes a normal follow-up proposal so the browser observes their genuine
outdated state. No review payload or SVG is inserted by the test. The production
HTTP routes compose both sides from the durable review store and the renderer
cache begins empty.

## Reproduction

Prerequisites are the pinned local image reported below and a Playwright native
Chromium executable. The documented operator launch remains:

```console
cascade up
```

Run the acceptance check from the repository root with a durable evidence
directory:

```console
CASCADE_ACCEPTANCE_ARTIFACT_DIR=/tmp/task_046_005_001-evidence \
  pytest -q tests/war_room/test_architecture_planning_browser_journey.py
```

The check writes `01-paired-review.png`, `02-approved-review.png`, and
`evidence.json`. The JSON records the native browser version, exact baseline and
changed/final proposed Git revisions, code/document/plan refs, all publication
operation IDs, Feature and Epic review-unit identities, the final reviewed
tuple, renderer settings, screenshot names, and pass/fail result. Keeping these
values runtime-generated prevents a copied identity from being mistaken for
evidence from a fresh fixture.

Renderer identity:

- image: `structurizr/structurizr@sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`
- settings: production `C4RenderSettings` defaults, recorded verbatim in
  `evidence.json`
- network: disabled by the production renderer command
- cache: fresh project-local `.cascade/c4-render-cache`

## Covered journey

The browser opens the real `/plan/{feature_id}` route after a server restart and
checks independently pinned, nonempty current and proposed SVG. It exercises
counterpart selection; added and removed elements and relationships; changed
views; drill/back; native hit, fit, zoom, keyboard selection; desktop and narrow
layout; and readable source/model/plan/design resources and diffs. It opens the
linked requirement and decision on both sides and creates all four semantic root
kinds (requirement, view, element, relationship).

The same page proves local and incoming reply persistence across reload,
blocking approval, authorized resolve/reopen, exact-tuple rejection, and a
removed current-side target that continues to block until explicitly resolved.
The fixture also proves empty-baseline acceptance, renderer-operation recovery
and reuse across restart, and a registered Epic-owned architecture proposal.
Focused backend suites retain the remaining failure/gate coverage described by
the parent feature.

Pass criteria are one passed test with no skip, two nontrivial PNGs, and an
`evidence.json` whose `result` is `pass`. Renderer timeout while other pinned
container acceptance jobs contend for the host is an environmental failure and
must be rerun uncontended; the production timeout is not relaxed.
