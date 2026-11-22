# Single C4 comparison implementation review

The pre-existing project-comparison and viewport-preservation changes were
committed as `213ffbe4`. The subsequent implementation follows the operator's
choice of one combined diagram. The uncommitted linked-viewport implementation
was removed; there is no optional two-pane comparison mode to maintain.

## Diagram impact inventory

| View / level | Owning design | Implementation and disposition |
| --- | --- | --- |
| `cascade-landscape`, `cascade-context` | Root DESIGN.md | Unchanged: no new person, external system, trust boundary or deployment. |
| `cascade-containers` | Root / War Room designs | Unchanged runtime boundaries: browser/HTTP projection stays in War Room; bounded renderer stays behind Workspace. |
| `cascade-war-room-components` | War Room DESIGN.md | Added Diagram comparison component, including the server preview projection and browser coordination. |
| `cascade-diagram-review-code` | War Room DESIGN.md | Added source-linked `initPairedC4Review`, `createPairedNavigation`, `createSemanticC4Viewer`, `draft_diagrams` and the Workspace comparison collaborator. |
| `cascade-comparison-render-code` | Workspace DESIGN.md | Added source-linked `attach_comparison`, `comparison_source` and `C4RenderScheduler`. |
| Comparison sequence | War Room DESIGN.md | Documents source-pinned admission, pending/failure handling, verified delivery and viewport restoration. |

The authored model, view inventory and semantic source contract were updated
together. Existing accepted snapshots and publication records were not rewritten.
Root REQ-ROOT-011 already covers the product goal and links to the owning designs;
its contract needs no duplicate local rendering requirements.

## Verification

- Source contract validation and the full pinned Structurizr renderer/cache test
  pass for the updated authored model.
- Real comparison renders verify retained removals, reviewed rename continuity,
  both connection variants after endpoint changes, isolated identities across
  views, and durable scheduler/cache reuse.
- The browser test uses a real rendered combined SVG and checks one canvas,
  red/green/amber states, before/after inspection, removed-target source-side
  routing, viewport preservation across selection/refresh, explicit Fit, and
  absence of linked-view controls.
- Browser navigation scenarios verify explicit Explore, ambiguity handling,
  parent navigation and project-preview/publication races.
- Node scenarios retain the original zoom/pan refresh regression, rapid rerenders
  before SVG installation and fitting a new pinned diagram.
- Failure checks reject missing endpoints and oversized source, expose pending
  and failed rendering without a partial diagram, and verify pinned metadata.
- Documentation relative links, Python lint for new modules/tests, and diff
  whitespace checks pass.

The renderer and browser fixtures do not publish or approve architecture.
Cold comparison creation adds one bounded union-layout render after the two
source snapshots become ready; subsequent polling reuses its pinned cache.


## Live inspection and navigation correction

War Room was restarted on port 34448. The project preview initially exposed a
real merge conflict in `cascade/workspace/DESIGN.md`. Local merge commit
`b0f6bce7` on `epic/epic_047` reconciles committed main while preserving both
preview-snapshot and work-ownership sections. The branch checks passed (17 tests).
The live preview then returned ready with 12 views, 52 identity changes across
7 affected views, one combined SVG, and no browser errors. No push or architecture
approval was performed.

Operator inspection identified a navigation regression: the combined viewer
selected expandable targets instead of following them, leaving the inspection
panel below the canvas. Click and Enter/Space now follow verified deeper views;
the Semantic targets list retains inspection without navigation. A browser
regression test verifies click, Level up, list inspection and keyboard navigation.
The README and War Room C4 requirement describe this interaction consistently.

Documentation review covers root/package/War Room/Workspace designs and both
READMEs. The authored C4 contract validates 12 views and 37 source symbols; source
and documentation links resolve. The navigation correction requires no model
change: the existing diagram-review Code view already links the changed
`createSemanticC4Viewer` and `initPairedC4Review` functions, and runtime/component
boundaries and renderer contracts are unchanged. Working-tree architecture
changes remain separate from the committed revisions used by the live preview.

Live browser verification also passed Cascade → context → Level up on the
running epic_047 page with no browser errors.
Navigation/color/browser regression checks passed: 7 tests (the unchanged native
renderer test was excluded from this interaction-only check).


## Equivalent landscape/context layouts

The live landscape and context both contain the same five elements and four
relationships: the authored landscape has one system and the context includes
all its surroundings. Independent derived identities caused independent layouts
and reversed dependency order. Equivalent displayed graphs now reuse one native
layout while retaining view-specific navigation and inspection metadata. Different
labels, descriptions, types, identities or endpoints keep separate layouts.
Workspace REQ-WORKSPACE-C4-006 owns this rule. The C4 model needs no topology change:
the existing comparison-source Code node still owns derived graph construction;
there is no new component or runtime boundary. The two authored scopes remain
separate so they can diverge when the architecture grows.

Eight comparison tests pass, including native rendering/cache validation, identical
SVG reuse with different navigation metadata, and isolation when labels change.
The live payload confirms that landscape/context share five elements and four
relationships, while L2 Containers contains War Room, Service and Repository
artifacts. README distinguishes these scopes; no C4 levels were collapsed.

After restart and an explicit retry of the interrupted render, live epic_047
verification passed: landscape/context have identical SVG geometry, L2 has a
distinct diagram, click-through and Level up work, and there are no browser
errors. Landscape remains available; changing the default entry view is a
separate UX recommendation, not part of the layout correction.


## Context entry and optional landscape

Following operator agreement, branch architecture browsing and comparison review
now start at system context when available. Comparison selection still prefers
an affected context when several exist. Explicit view selections, saved links and
polling retain their selected view, including landscape. Level up excludes
landscape and stops at context. Missing-context models use another available
view; landscape-only models remain usable.

The owning requirement is War Room REQ-WARROOM-C4-001. Root README, package DESIGN,
War Room DESIGN and the C4 source README agree on Context → Containers → Components
→ Code as the normal path. Workspace layout-sharing requirements remain accurate.
The Semantic navigation node in `cascade-diagram-review-code` now describes
context entry and optional landscape; its identity, source symbol, relationships
and view membership are unchanged, so the source contract needs no inventory
change. Landscape/context/container boundaries are retained: this is a navigation
policy, not a change to the modeled systems. Root DESIGN links to these owning
contracts and needs no duplicate requirement.

Verification: five UI/navigation tests passed, including initial context,
container drill-down, Level up at context, explicit landscape selection,
keyboard navigation, refresh preservation and landscape-only fallback. The HTTP
snapshot test places landscape first in the payload and verifies context is the
initial selection. Fifteen source/native-render checks passed for the authored
C4 model. All 37 C4 source symbols and reviewed documentation links resolve;
whitespace checks pass. No accepted snapshots or approval receipts were changed.
The existing staged review is marked stale (`artifact_changed`) after proposal
reconciliation; that invalidation is retained in the review registry.

Live verification after restarting War Room passed on epic_047: default context,
Cascade → Containers, Level up stopping at context, optional landscape selection
and return to context, with no browser errors. The related project-color and
plan-comparison suite also passed (14 tests).

Pre-push validation: the configured repository review regression gate passed
(116 tests). New comparison modules/tests pass lint and staged whitespace checks.
