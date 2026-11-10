---
id: epic_046
title: Complete C4 plan review and add branch architecture browsing
tier: epic
status: active
parent: null
children: []
depends_on:
- epic_034
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Complete C4 plan review and add branch architecture browsing

## Intent

When a new feature reaches plan review, opening its plan in a running War Room must show the actual current and proposed C4 diagrams side by side, next to its proposal, with working navigation and semantic comment threads. The same experience applies to epic proposals. Review must cover the exact revisions displayed. This must work through the normal planning and UI entry points, without manually injecting a payload, editing review stores, or invoking internal Python helpers.

Add an **Architecture** tab to the War Room so a user can explore the current branch's versioned C4 views independently of a proposal. Show related requirements and design decisions as contextual documentation, without imposing an artificial one-to-one correspondence between C4 levels and DESIGN.md files.

This is integration and completion of Epic 034, plus a branch architecture browsing surface. Reuse its renderer, semantic identities, review units, documentation routing, comment storage, and lifecycle gates. Do not replace them with a parallel architecture system.

### Success criteria

1. A normally planned new feature opened in the running War Room displays real current/proposed C4 diagrams beside its proposal at the exact reviewed revisions.
2. Semantic navigation, change highlighting, requirement/diagram threads, replies, resolution, source/diff links and revision-bound approval work through production HTTP routes.
3. An Architecture tab explores an identified branch snapshot with verified requirement/decision context and correct split-repository provenance.
4. Real-renderer and real-browser acceptance proves the complete new-feature review journey, branch exploration, failure handling and restart recovery. Isolated helper/DOM tests alone cannot satisfy acceptance.

## Macro-architecture

The following findings and requirements guide planning; the Epic Team develops the implementation architecture after activation.

### Current implementation and verified gaps

These findings describe the repository at the time of this brief. Recheck the named boundaries during implementation and distinguish newly discovered defects from working infrastructure.

| Boundary | Current implementation | Gap to close |
| --- | --- | --- |
| Plan page to HTTP API | `cascade/war_room/static/plan_viewer.js` fetches `/api/doc/{id}` and calls `initPairedC4Review` only if `doc.paired_review` exists. | The live page silently omits the entire architecture review when this field is absent. It needs a real response contract and explicit states. |
| Plan API to review composition | `WarRoomHandler._handle_doc` in `cascade/war_room/server.py` serializes the plan and optionally adds epic readiness. `cascade/war_room/serialize.py` does not compose paired review data. | No `paired_review` field is supplied. `compose_c4_review_payload` in `cascade/workspace/c4_review.py` has no production caller connecting it to the plan page. |
| Planning to usable artifacts | Versioned models, scoped staging, review units, revision checks, and render operations exist under `cascade/workspace/`. | Existing helper implementations do not prove that normal new-feature planning produces and exposes all artifacts needed by the live page. Trace this path and repair any missing publication, scheduling, discovery, and restart recovery steps. |
| Artifact loading | The UI can consume inline SVG or fetch a supplied SVG URL. The composer validates bound artifacts and produces semantic SVG. | Select and implement one supported delivery contract, tied to immutable authorized artifacts, and prove it through HTTP. A local artifact path is not a browser URL. Never expose arbitrary filesystem paths. |
| Navigation contract | The UI supports `drill_view_key` and `drill_level` on targets. Backend `C4ReviewTarget` currently carries only `kind` and `semantic_id`. | Derive and expose verified drill destinations from model containment and explicit view membership. Payload connection alone does not complete drill-down. |
| Change presentation | The backend has semantic diffs and the UI has a legend, summary, and selected-target highlighting. | Verify actual per-element and per-relationship added/removed/changed styling. A legend or changed-view list alone is insufficient. Preserve changes when selecting targets. |
| Semantic comments | Typed anchors, comment persistence/routing, a semantic composer, and blocking logic exist. The server accepts semantic-anchor-shaped comments through the generic endpoint. | The semantic UI is unreachable when paired review is absent. The HTTP write path shown validates anchor shape and posts a generic comment; wire authoritative target/revision/owner validation using the pinned review, rather than trusting client fields. Ensure read freshness is equally authoritative. |
| Thread lifecycle in UI | The paired panel renders semantic roots and can create them; the existing plan-comment renderer treats semantic threads separately. | Verify and complete reply, incoming-reply refresh, human resolution, and reopen behavior where supported. New semantic roots must participate in the existing conversation and routing lifecycle, not become an isolated root-only list. |
| Verification | `tests/war_room/paired_c4_review_cases.mjs` directly supplies fabricated payloads to exported JS functions using a deterministic DOM fixture. Existing backend suites cover useful individual contracts. | These tests do not establish that a normally planned feature opened in a real browser receives real artifacts. Add acceptance coverage across planning, HTTP, SVG loading, native browser interaction, comments, and approval. |
| Independent exploration | The reviewed War Room template has operational panels, and the paired viewer is attached to proposal review. | Add a discoverable Architecture tab with explicit branch/revision provenance and a reusable single-model navigation surface. |

Useful implementation entry points: `cascade/war_room/server.py`, `serialize.py`, `templates/war_room.html`, `templates/plan_viewer.html`, `static/plan_viewer.js`, `cascade/workspace/{architecture_review,c4_render,c4_review,c4_diff,c4_threads}.py`, and the existing comment and scoped blocking modules.

### Requirements

#### 1. Complete the normal planning-to-review path

1. Trace a feature from normal creation and planning through architecture context, staged model/design changes, review-unit publication, rendering, and plan review. Use the same authorized tools and workflow available to its team.
2. For a feature claiming an architecture change, publish an immutable review unit binding the plan, requirements/design documents, accepted baseline, proposed source, repository identities, integration lineage, renderer settings, and exact revisions before approval becomes available.
3. Schedule render work through the existing bounded background operation. The HTTP page request must not start an unbounded renderer or execute project content. Render availability and reviewability must be durable or reconstructible after restart.
4. Resolve current architecture from the accepted pointer on the owning integration lineage. Resolve proposed architecture from the feature's staged review artifacts. Never label a planning-only ancestor proposal, another worktree's HEAD, or target trunk as the accepted current state for a different lineage.
5. A first model shows an explicit empty current side and a real proposed diagram. A legitimate no-diagram-change proposal says so and retains access to the current model where available. Missing artifacts for a claimed change are an error/pending condition, never a successful no-change result.
6. Historical plans without a review unit have a visible explanatory state. Do not synthesize reviewed evidence for old work merely to populate the UI.

#### 2. Connect the real HTTP review contract

1. Supply `paired_review` through `/api/doc/{id}`, or an explicit same-origin review-resource reference that the page always follows. Document the chosen schema and add a contract test against the actual handler.
2. Return explicit states for loading/pending, ready, no diagram change, empty baseline, absent/removed view, unsupported model, render failure, missing legacy review, stale revision, and partial acceptance. Include actionable reasons and exact source/diff links.
3. Present repository, branch or lineage, full revision in details, shortened revision in labels, and review-unit identity. Labels must describe the same artifacts that supply the SVG, target bindings, requirements, and decisions.
4. Serve only sanitized SVG with verified bindings, using either bounded inline content or immutable same-origin artifact URLs. If URLs are chosen, validate repository/work scope and artifact membership on every request; use artifact identity/digest rather than caller-supplied paths. Retain the existing SVG safety boundary.
5. A failed or delayed architecture request must leave plan text and existing comments usable. Show status and retry controls inside the architecture region. Do not hide the region because optional data is absent.
6. Refresh on completed render, newly published review, or stale-baseline change without a full reload where practical. Preserve selection, thread drafts, and navigation if their targets still exist. Bound polling and stop it when the page is inactive or closed.

#### 3. Deliver the complete paired review interaction

1. Place the current/proposed diagrams beside or immediately adjacent to the plan, with usable space at desktop widths and an accessible stacked layout on narrow screens.
2. Offer a view/level selector covering all relevant views, with every changed view clearly identified and reachable. Both sides use the same explicit view key and level.
3. Selecting an element or relationship on either side highlights its semantic counterpart. Added/removed objects remain visible with an explicit absent counterpart. Never match by label, coordinates, array order, or exporter-local IDs.
4. Derive deterministic drill destinations for containers/components from the validated model and available views. When multiple views are appropriate, offer labeled choices; when none exist, explain that no deeper view is available. Shared back navigation restores both sides and their selection.
5. Provide pan/zoom, fit-to-view, readable labels, keyboard-accessible target selection or an equivalent semantic target list, and visible focus. Native browser behavior must be checked, including SVG import, hit testing, and view sizing.
6. Visually distinguish added, removed, and changed elements AND relationships using semantic diff data, with a legend and accessible text summary. Selection styling must coexist with change styling. Layout-only changes must not appear as architecture changes.
7. Source, model, plan, and design-document diff links must open actual readable content at the displayed revisions. A textual reference string without a working destination does not satisfy this requirement.

#### 4. Finish semantic comments and revision-bound approval

1. Allow comments on a requirement, view, element, or relationship from the actual review page. Show the selected target, side, repository, and revision before submission.
2. Validate the anchor on the server against the current authorized immutable review tuple and pinned target inventory. Reject nonexistent targets, forged repositories/revisions, wrong work owners, and stale submissions with a clear refresh/review action.
3. Persist through the existing thread store and routing path. Support replies, incoming updates, and authorized human resolution using existing permissions. Existing Markdown comments continue to function.
4. Read-time freshness and original source/diff links must remain valid after refresh and restart. Removed targets and revision drift appear as outdated; an outdated blocking thread remains blocking until authorized resolution. Reuse the explicit reviewed rename policy; never infer continuity from labels.
5. The approval action binds the exact plan/design/model tuple displayed. Recheck this tuple server-side at submission and at existing downstream boundaries. A browser tab showing an old tuple must not approve a replacement tuple implicitly.
6. Demonstrate that a blocking semantic thread prevents approval and affected downstream work, while unrelated work remains available. Resolution restores eligibility only when all other readiness conditions also hold.
7. Partial split-repository acceptance must show which side landed and which remains pending; neither the UI nor downstream gates may claim full architecture acceptance early.

#### 5. Add a War Room Architecture tab

1. Add an accessible top-level **Architecture** tab alongside the board experience. Keep existing operational surfaces available and preserve the selected tab in navigation state.
2. Default to the target checkout/worktree associated with the current War Room session. Display repository, branch, and pinned commit prominently. With multiple relevant worktrees, provide an explicit branch/worktree selector limited to known project contexts; never guess from whichever agent branch changed most recently. Detached HEAD displays its commit accurately.
3. Browse the versioned model at the selected branch's pinned HEAD snapshot. Label this as branch architecture, independently of whether it has been accepted through a review. Offer an explicitly labeled accepted-lineage reference when one exists; never conflate branch content with accepted architecture.
4. Resolve architecture through the configured target/tracking destination and existing stable mappings. In split repositories, show both the code ref and the documentation ref. Use a recorded branch/review/lineage association to choose the documentation revision. If no association exists, ask the user to select a known documentation ref or show an unavailable state; never silently use tracking HEAD and label it branch architecture.
5. Start with context or container views when available, otherwise a sensible available view. Provide view switching, semantic selection, relationship details, drill-down, back, pan/zoom, and fit-to-view by reusing review viewer primitives.
6. Pin the browsing session to a commit. When branch HEAD changes, show an update indicator and refresh action; do not mix views or documentation from two revisions. Do not silently render dirty worktree edits as committed architecture. An optional future preview may be labeled separately but is not required here.
7. Use the same controlled background render/cache and artifact serving contract as plan review. Show loading, missing model, unsupported source, and failure states with source access and retry guidance. Tab activation must not stall the board or trigger repeat rendering on every board refresh.
8. Support reloadable deep links including repository context, pinned ref, view key/level, and selected semantic target. Invalid or unavailable links explain what cannot be resolved.
9. Browsing does not create a review unit or approval. Offer “Open plan review” only when a specific associated proposal exists. Semantic review comments belong to that proposal; do not invent a separate branch-wide comment system in this scope.

#### 6. Show requirements and design decisions as linked context

DESIGN.md boundaries follow ownership, directories, behavior, and interfaces. C4 levels follow architectural abstraction and views. Their relationship is many-to-many: a container can be described by several directory designs, while a cross-cutting design decision can affect several views or elements. Do not create duplicate designs per C4 level or assume a directory nesting level equals a C4 level.

1. Add a contextual **Requirements & decisions** panel to the Architecture tab and paired review surface. It should supplement the diagram and preserve access to the full documents.
2. Use existing stable requirement/decision IDs, explicit citations, design mappings, model ownership, and reviewed associations to relate documents to views/elements/relationships. Extend the mapping contract only where necessary; record provenance and pinned document revision.
3. On target selection, show explicitly linked requirements, decisions/rationale, owning design documents, and source section links. With no selection, show view-level links and a clearly labeled broader design index.
4. Separate explicit links from broader owner/directory context. If there is no explicit target mapping, say so and offer relevant owning designs without claiming target-level coverage. Do not fabricate links from similar names or prose.
5. In review, show proposed documentation and access to its current version/diff. In branch browsing, use documentation belonging to the selected snapshot/recorded cross-repository association. Display a missing or stale reference visibly.
6. A selected requirement can start its semantic thread in proposal review. Decisions remain readable and linkable; a new decision-specific thread anchor type is not required by this brief.
7. Keep document loading bounded and lazy. Avoid loading every DESIGN.md on each board refresh. Render Markdown using the existing safe presentation rules.

### Delivery slices

1. **Production contracts and planning publication:** trace a new feature; close render/publication/discovery gaps; define revision-pinned HTTP/artifact contracts and explicit states; connect the plan endpoint to composition.
2. **Paired viewer and comments:** complete drill metadata, change styling, real SVG loading, source links, semantic thread lifecycle, server validation, and tuple-bound approval from the live page.
3. **Branch architecture browser:** add the War Room tab, explicit branch and documentation-ref resolution, shared viewer navigation, revision updates, and deep links.
4. **Documentation context:** expose verified many-to-many requirement/decision/design links with pinned provenance and clear unmapped states.
5. **Acceptance and closeout:** run the end-to-end scenarios below, retain evidence, and update user/operator guidance. Do not mark the feature complete solely from helper/DOM suites passing.

### Required acceptance evidence

The primary test is a normal user journey on a fresh fixture project using the real local renderer and a real browser against a running War Room. A deterministic agent/provider fixture may supply planning responses, but it must use normal planning tools and publication paths. Do not seed review JSON by hand, substitute fabricated paired payloads, mock the document endpoint, or replace rendered diagrams with placeholder SVG in the primary acceptance scenario.

#### A. New-feature plan review: release-blocking proof

1. Create a project with a small versioned accepted architecture and a normally created epic/feature. Start from a clean render cache.
2. Have the new feature's planning flow propose a meaningful container/component change and a relationship change, including linked requirement and decision evidence. Reach the ordinary plan-review state through supported tooling.
3. Launch War Room with the documented launch command, open the new feature through its normal board/review link, and wait for any bounded background rendering.
4. Assert that actual current AND proposed SVG diagrams are visible, nonempty, correctly labeled, and match the independently checked pinned model revisions. Confirm that the plan text is available beside or adjacent to them.
5. Select elements and relationships in both directions; verify counterpart highlighting. Exercise an added/removed target, changed-target styling, all changed views, drill-down, and back using actual browser pointer/keyboard events.
6. Open linked requirement/decision content and real source/model/plan/design diffs. Verify that each destination uses the displayed revisions.
7. Post requirement, view, element, and relationship threads through the page. Reply, receive an incoming team reply, reload, and verify persistence, ownership routing, original links, and target navigation.
8. Make one thread blocking; attempt approval through the actual UI and verify server rejection. Resolve it as the authorized human and verify approval eligibility. Mutate a bound artifact and prove the previously displayed tuple cannot be approved.
9. Regenerate the proposal after a target is removed and verify retained outdated thread behavior. Restart War Room and verify recovery without rebuilding evidence manually.
10. Repeat the core visible paired-review and provenance check for an epic proposal.

#### B. Current branch exploration

1. Open Architecture from the running War Room; verify that its default branch/worktree and commit are the session's actual context.
2. Browse context/container/component views where present; select a relationship, drill, navigate back, and use pan/zoom/fit. Read linked requirements and decisions and open their pinned source sections.
3. Select a second known branch with a deliberately different model. Verify that diagrams and documentation change together and carry correct provenance. Reload a deep link and recover its pinned selection.
4. Advance the selected branch; verify an update indicator followed by an explicit snapshot refresh. Check detached HEAD, dirty edits, missing model, and missing deeper view behavior.
5. Exercise a split documentation destination with distinct code/documentation commits. Verify recorded association and an explicit unavailable/selection state when association is absent.

#### C. Failure and lifecycle coverage

Cover first model/empty baseline, justified no diagram change, old plan without review unit, pending render, renderer failure, invalid semantic binding, stale baseline, missing artifact, stale comment submission, and partial cross-repository acceptance. Assert visible explanations and appropriate approval holds, with plan text still usable. Check an unrelated feature remains unblocked by a local blocking thread.

Use focused backend/API tests for tampered anchors, authorization, immutable artifact lookup, revision races, and cache invalidation. Retain existing unit and DOM tests as supporting coverage. Use a real-browser check for layout, actual SVG hit targets, fit/zoom, and both tab and plan routes. Avoid making every lifecycle permutation an expensive browser scenario.

#### D. Evidence retained at closeout

Record exact launch/test commands, renderer image/settings, fixture/source revisions, code and documentation repository refs, review-unit/tuple identity, test results, and screenshots or a short recording of both paired review and branch browsing. State prerequisites for running the renderer and browser checks. A skipped real-renderer/browser scenario is an unmet release criterion, not a passing acceptance result.

### Completion criteria

- A newly planned feature opened through the running UI displays real revision-correct C4 diagrams side by side with its plan, without internal manual setup.
- Diagram navigation, semantic commenting/replies/resolution, actual diffs, and revision-bound approval operate through production HTTP routes.
- War Room's Architecture tab explores a clearly identified branch snapshot and linked documentation, including split-repository provenance.
- Requirements and decisions provide useful verified context without forcing DESIGN.md and C4 into a one-to-one hierarchy.
- The primary end-to-end acceptance evidence exists and passes. Documentation completion and isolated component tests alone do not close this work.

## Cross-module constraints

Use the normal Epic/Feature/Task planning and human approval workflow. Keep this epic in backlog until activation; do not create child work or implement its requirements while filing this brief.

Reuse Epic 034 infrastructure and preserve exact revision and authorization boundaries. Relate requirements and decisions many-to-many to C4 views, without imposing a one-to-one hierarchy with DESIGN.md files.

The detailed requirements and acceptance evidence define the intended outcome; the Epic Team owns implementation decomposition.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-10 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
