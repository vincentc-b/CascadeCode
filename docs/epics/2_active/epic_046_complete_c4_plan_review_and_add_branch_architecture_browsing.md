---
id: epic_046
title: Complete C4 plan review and add branch architecture browsing
tier: epic
status: active
parent: null
children:
- feat_046_001
- feat_046_002
- feat_046_003
- feat_046_004
- feat_046_005
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

The findings and requirements below define the scope. The final implementation contracts record the Epic Architect decisions for the activated plan.

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

### Final implementation contracts

These contracts resolve the activation questions and bind all five features. They describe work to implement, not capabilities already delivered. Existing `ArchitectureReviewStore`, ownership routing, semantic diff/binding validation, renderer and comment/gate services remain authoritative.

#### Publication, scheduling and recovery

- Add an authenticated `publish_architecture_review` adapter to the normal epic and feature tool registries and MCP schemas, with matching planning instructions. Derive actor, owning work and `ProjectContext` from the invocation, never from client assertions. Accept the exact committed proposal references, expected plan revision and accepted-baseline generation. Reuse `ArchitectureAuthoringIntent` / `stage_owned_architecture_change`: owned proposals stage; ancestor-owned proposals route to the owner and cannot become locally reviewable. Include an explicit `no_diagram_change` declaration with rationale; missing publication is not that declaration.
- Publication first validates ownership and pinned input inventory, then durably records an idempotent publication intent. Return its operation ID and pending state without waiting for Docker. A worker uses the existing staging/validation operations and publishes the staged review unit and semantic diff only after validated artifacts exist. Recheck plan revision, destination and accepted generation before making that unit current. Superseded work may retain historical evidence but cannot replace the active unit. Repeated publication of the same input tuple returns the same operation; changed inputs require a new tuple. Approval of newly participating plans stays held while publication is pending or invalid. Legacy plans retain an explanatory missing-review state under the existing rollout policy, without invented evidence or a new global approval exemption.
- Reuse `C4ArtifactRenderer.submit` behind one project-scoped scheduler shared by publication and branch browsing. Its current per-call daemon thread is not the scheduler. Deduplicate by closure digest, pinned image, adapter/artifact format and all render settings. Default to one active render and at most 32 admitted pending operations per project; excess admission returns `queue_full` with retry guidance. Coordinate ownership across processes using the project's existing locking conventions so two servers cannot publish competing jobs. HTTP GETs read state and artifacts; they never wait on Docker or invoke rendering. An explicit branch-snapshot POST or retry POST may admit bounded background work.
- Persist operation inputs, owner/snapshot association, render identity, state, attempts and failure reason atomically in project-local operational metadata. This is a job ledger, not another review/acceptance store. Preserve the existing 90-second render timeout, offline confinement and resource settings. Capture a versioned render-identity binding in the reviewed tuple (extend the unit schema compatibly if needed); settings or binding-adapter changes cannot silently reuse human review. Old units keep their original digest semantics and cannot be upgraded into newly reviewed evidence automatically.
- At startup reconcile pending/running intents and staged-unit discovery against immutable Git inputs and validated cache manifests. Reuse complete verified artifacts, discard only operation-owned incomplete output, and reclaim an interrupted operation only after its previous worker lease is no longer live. Allow one automatic recovery attempt per operation, durably counted; further failure requires explicit retry. Retry never changes the tuple or renews approval. Missing/corrupt cache is rebuildable from the exact original sources; missing source objects, hash mismatch or changed baseline becomes an explicit failure/stale state. Never reconstruct from current HEAD. Completion and replacement update the same durable work-to-current-unit discovery record, recoverable if the process dies between staging and indexing.

#### HTTP, immutable resources and bounds

- `/api/doc/{work_id}` always includes a small `paired_review` envelope for epic/feature plans: `schema_version: 1`, `state`, stable `reason_code`, readable `message`, `resource_url`, nullable `review_unit_id` / `reviewed_tuple_digest`, and retry metadata. Use `/api/architecture/reviews/{work_id}` for the current review projection. Plan text and Markdown comments load independently; architecture failure must not fail the document response or hide the panel. The client always follows the resource reference.
- The review projection extends the existing composer rather than duplicating its validation. It supplies work/owner identity, unit/digest, plan revision, accepted pointer/generation and integration lineage; repository identities and full pinned code/document revisions; all view keys/levels and changed-view inventory; per-side availability; validated semantic target inventories, per-target diff state and labeled drill choices; source/model/plan/design diff resource links; context links; and authoritative reviewability/blocking reasons. Lists and per-view details may be paginated/lazy, but every changed view must remain discoverable. Do not transfer every SVG or DESIGN.md in the index response.
- Normalize wire states to `pending`, `ready`, `no_diagram_change`, `empty_baseline`, `missing_model`, `missing_review`, `unsupported_model`, `render_failed`, `invalid_artifact`, `stale_revision`, `partial_acceptance`, and `unavailable`. Per-view/side states additionally distinguish `present`, `absent` and `removed`. Translate current composer states explicitly: `first` is empty baseline; `unchanged` does not by itself prove an explicit no-diagram-change declaration. An empty baseline with a validated proposed diagram can be reviewable. Missing artifacts for a claimed change, unsupported input, failed validation and stale evidence cannot be reviewable. Partial acceptance includes code/document landing states from the existing promotion journal and never signals full acceptance. Carry reason and available pinned source links in every state.
- Choose immutable same-origin SVG URLs, not inline SVG, for both surfaces. Use `/api/architecture/artifacts/{scope_id}/{artifact_id}` where scope is an authorized review unit or branch snapshot and the opaque artifact ID resolves through its server-owned manifest. Use `/api/architecture/resources/{scope_id}/{resource_id}` for readable pinned source, documents and source/model/plan/design diffs. Resource descriptors fix repository, commit, file or diff endpoints and optional verified section; no caller filesystem path, arbitrary Git expression or shell command is accepted. Convert internal `revision:...` strings into actual readable resources. Historical resources remain resolvable for existing thread anchors while their source evidence is retained.
- On every lookup verify current project/work or branch-context access, exact scope membership, repository identity, manifest and content digest, path confinement and same-render semantic bindings. A content hash is not authorization. Serve only sanitized, semantically annotated SVG through this route, with `image/svg+xml`, `nosniff` and restrictive content policy; never serve renderer HTML/scripts. Digest the final sanitized/annotated bytes. Cache entries are immutable per scoped identity; use private revalidation with ETags so access is rechecked. Mutable review/status responses use no-store. Unknown/out-of-scope identifiers return 404; stale write expectations return 409; malformed input 400; supported explicit retries return 202; admission exhaustion 429. Ordinary architecture lifecycle states return 200 JSON so the panel can explain them.
- Initial defaults: metadata pages at most 256 KiB encoded UTF-8, SVG at most 4 MiB per view, source/document/diff pages at most 1 MiB, and JSON mutation requests at most 256 KiB. Enforce read/output limits before unbounded materialization. Paginate inventories and readable large text with stable cursors pinned to the same scope; an oversized indivisible SVG reports `artifact_too_large`, never silent truncation or incomplete evidence marked ready. The first feature names/tests these constants and measures the real smoke fixture against them.
- Refresh status only while the page/tab is visible: one in-flight request, 2-second initial interval with backoff capped at 15 seconds, stopping after two minutes pending with a visible manual retry. Resume on visibility or explicit action. Check for newly published tuples and baseline drift on focus and before mutations. Preserve drafts and navigation when targets survive; stale drafts require explicit review before submission. Responses from an old selection/request generation cannot overwrite a newer snapshot.

#### Shared freshness, semantic interaction and approval

- Implement one authorized review-context resolver over the existing review store and gates. Document/status reads, semantic-thread reads and writes, human approval, dispatch, integration, merge and closeout share its tuple and baseline validation. Separate cheap status reads from expensive rendering; approval may validate cached evidence but cannot start a renderer. Revalidate expected plan revision, unit ID, tuple digest and baseline generation under the existing serialized mutation boundary immediately before writing approval; concurrent replacement must fail instead of approving unseen content.
- Semantic roots use existing `create_semantic_thread`, anchor validation and routing. Resolve owner/repository/revision/source links from the pinned server inventory; reject client substitutions. Requirement anchors use the actual pinned requirement document provenance, including tracking repositories, rather than borrowing a diagram-side repository. Keep replies and authorized resolve/reopen operations in the current thread lifecycle. Read-time freshness compares retained anchors to the active unit; outdated blocking threads stay blocking, with original sources intact, until authorized resolution. Do not extend the anchor kinds to decisions or add branch-wide comments.
- Share a semantic single-view renderer/navigation module between paired review and branch browsing; pair coordination, diff overlays and review comments are adapters around it. Drill choices come from validated containment and explicit view membership on each side, sorted deterministically by level/key with labels. Paired navigation selects one key/level for both sides and visibly represents a missing side. Back restores both selections. Target identity remains kind plus semantic ID; relationship details and diff classes survive selection. An accessible semantic target list supplies keyboard equivalence to SVG hit targets.

#### Branch provenance and documentation context

- Expose known contexts through `/api/architecture/contexts`, derived from the War Room session's configured target repository/worktree and registered project contexts. Default to that target checkout, not the tracking root or latest agent worktree. Resolve a selected context once to a full commit; show detached HEAD accurately. Create an immutable browsing snapshot through `POST /api/architecture/snapshots`; fetch it through `/api/architecture/snapshots/{snapshot_id}`. These operations do not create a review unit or acceptance.
- Snapshot identity binds target/code repository and commit, destination mapping revision, documentation repository and commit, source/closure and render identity, plus association provenance. Read design mappings and model/document bytes at those commits, not mutable worktree paths. For colocated documentation use the selected commit. For split repositories use an exact recorded code-ref-to-document-ref association from review/promotion/lineage evidence. A record for an ancestor or another branch is not an exact association. When no unique association exists, show `documentation_ref_required` and allow selection only among known documentation refs. Resolve that selection to a commit and label it explicitly user-selected, not accepted or verified branch association. Never fall back to tracking HEAD. Record this selection in the reloadable snapshot.
- Show branch snapshot content separately from an optional accepted-lineage reference, including both code and documentation refs. Partial promotion or ambiguous association remains visible. Offer Open plan review only for a proven specific proposal association. Head checks produce an update indicator; explicit refresh creates a new snapshot and switches diagrams/documentation atomically. Dirty edits never enter committed content. Deep links carry known context ID, snapshot ID (which pins full refs), view key/level and optional semantic target. Restart reconstructs the same snapshot from durable descriptors; unavailable commits/contexts or invalid targets receive an explanation rather than substitution.
- Context descriptors bind requirement/decision IDs, document repository/commit/path/section, target/view identities and relation provenance. Use stable citations, reviewed explicit associations and existing ownership mappings as many-to-many edges. Present explicit links separately from owner/directory context and the broader design index; unmapped targets say so. No name similarity or directory-depth inference. Extend the existing versioned mapping contract only when necessary; a new context cache is a derived projection, not a new source of truth. Load selected context/documents lazily through the same scoped resources and existing safe Markdown presentation. In review, proposed documentation also links to the exact current version/diff; missing or stale refs remain visible.

#### Verification ownership

`feat_046_001` owns the tool adapters, publication/recovery resolver, HTTP/resource schema and early real-renderer/browser smoke; `002` completes shared viewer and mutation/gate integration; `003` adds branch snapshots; `004` adds context projections; `005` records final integrated A–D acceptance. Their existing serial dependencies and full brief obligations remain unchanged. Fix the renderer test's recursive copied-file inventory mismatch without relaxing strict closure validation. The first smoke must create/publish through registered team tools, open the normal plan route, load real current/proposed SVG through these HTTP resources, and recover after a server restart. Include a focused crash/retry and stale-write race test; use API tests for authorization and state permutations. Native browser evidence remains necessary for SVG hit testing, layout and navigation. Installed dependencies and supporting helper tests do not satisfy this milestone.

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

Use the normal Epic/Feature/Task planning and human approval workflow. This epic is activated; its five children remain in backlog until the final plan completes role review and human approval.

Reuse Epic 034 infrastructure and preserve exact revision and authorization boundaries. Relate requirements and decisions many-to-many to C4 views, without imposing a one-to-one hierarchy with DESIGN.md files.

The detailed requirements and acceptance evidence define the intended outcome; the Epic Team owns implementation decomposition.

## Core dependencies

- Work prerequisite: epic_034 is canonically completed; its renderer, immutable review units, semantic IDs, design mappings, thread store and lifecycle gates remain the foundation.
- Canonical software dependency manifest revision 2 is ready. Checks ran against the existing host runtime for /home/ubuntu/dev/CascadeCode (the dependency executor's project target); implementation stays in the owned integration worktree. No install or upgrade is requested or authorized.
- Verified installed versions: Python 3.12.8; pytest 9.0.3; PyYAML 6.0.3; cursor-sdk 1.0.37; langgraph 1.2.14; langgraph-checkpoint-sqlite 3.1.1; Node 20.20.2; Docker server 28.0.0; Playwright 1.64.0; Chromium 156.0.8078.4.
- The existing local renderer image is structurizr/structurizr@sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c. Keep the renderer's bounded offline settings and sanitizer/binding validation. Browser launch and image availability are verified prerequisites, not end-to-end acceptance.
- Baseline check on activation: `python -m pytest -q tests/workspace/test_c4_render.py::test_real_pinned_renderer_publishes_one_validated_handoff_and_cache` failed (1 failed): the fixture copies nested final-validation evidence but declares only top-level files, so strict closure validation reports extra files before rendering. feat_046_001 owns repairing the fixture and proving actual rendering. Do not weaken inventory validation or describe this failing check as a pass.

## Feature breakdown

All five features are minted in backlog. Dependencies form a deliberate serial chain to keep shared server/viewer changes coherent and reuse one evolving acceptance fixture.

| Feature | Depends on | Deliverable and epic coverage |
| --- | --- | --- |
| feat_046_001 — Connect normal architecture planning to revision-pinned HTTP review | None within epic | Requirements 1–2; production planning/publication/render/recovery path, explicit HTTP states, verified artifact/provenance/inventory contracts, real source/diff resources, drill/change metadata and an initial real-browser smoke. |
| feat_046_002 — Complete live paired C4 navigation comments and exact-tuple approval | feat_046_001 | Requirements 3–4 and client refresh from 2; shared semantic viewer, native SVG navigation, semantic conversation lifecycle, authoritative validation and displayed-tuple approval. |
| feat_046_003 — Browse pinned branch architecture from the War Room | feat_046_002 | Requirement 5; tab, known branch/worktree selection, pinned snapshots, split documentation refs, update indicators and deep links using shared viewer/render services. |
| feat_046_004 — Show verified requirements and decisions beside C4 views | feat_046_003 | Requirement 6 on both surfaces; explicit many-to-many context, safe lazy document loading, pinned sources/diffs, unmapped states and requirement-thread entry. |
| feat_046_005 — Prove the complete C4 review and branch exploration journeys | feat_046_004 | Acceptance A–D and all completion criteria; final integration repairs, reproducible real renderer/browser journeys, screenshots and operator guidance. |

The first feature starts the real user-journey fixture and each subsequent feature extends it. The final feature consolidates evidence at the final integrated revision; it is not the first point at which production-path feasibility is tested. Every detailed brief requirement remains binding. Scope exclusions: another renderer/review/thread store, branch-wide comments, decision-specific anchors, dirty-worktree preview, inferred document coverage, per-C4-level DESIGN.md duplication, and unrelated refactoring.

## Open questions

None outstanding for architecture planning. The final implementation contracts resolve HTTP/artifact delivery, normal publication and restart recovery, shared freshness, branch/document provenance and early acceptance ownership. No architecture amendments were pending at review; no dependency installation or human scope decision is needed.

The Epic Architect will sign the saved final revision after review. The Epic Manager must independently review and sign that same revision before human plan approval. The failing renderer fixture remains assigned to feat_046_001; no implementation or acceptance pass is claimed by this planning update.

## Decision log

- 2026-11-10 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-10 · Epic Manager · **Feature breakdown**
  Chose Deliver feat_046_001 through feat_046_005 as a serial chain: production publication/HTTP contracts, paired interaction and semantic approval, branch browsing, verified documentation context, then integrated acceptance and guidance..
  Rationale: The same server, semantic viewer and immutable provenance contracts span the slices. Serial dependencies reduce conflicting implementations and allow each feature to extend one production-path acceptance scaffold. Keep all requested functionality; exclude unrelated refactoring and new parallel architecture/comment systems.
  Honors: All epic_046 detailed requirements and completion criteria; reuse Epic 034 infrastructure; frugal engineering and product scope constraints..

- `dec_002` · 2026-11-10 · Epic Manager · **Required acceptance evidence**
  Chose Start the real planning/renderer/browser smoke in feat_046_001 and extend it through each feature; feat_046_005 must retain passing A-D evidence at the final integrated revision. Assign the discovered renderer fixture inventory failure to feat_046_001 without weakening closure validation..
  Rationale: The production connection is the core risk. Dependency checks confirm installed tooling and a browser launch, but the existing renderer test fails before rendering because its copied nested evidence is absent from its declared inventory. Treat that as a concrete early repair and do not defer feasibility or mistake unit/DOM coverage for acceptance.
  Honors: Release-blocking real-renderer and real-browser proof, immutable source safety and the brief's prohibition on fabricated primary acceptance payloads..

- `dec_003` · 2026-11-10 · Epic Architect · **Final implementation contracts — HTTP and immutable resources**
  Chose Use an always-present paired_review envelope and a lazy review resource, with scoped immutable same-origin SVG and source/document/diff URLs. Reuse the existing composer, binding validation, semantic viewer and review-context resolver; enforce explicit states, payload limits and exact displayed-tuple validation for comments and approval..
  Rationale: The current document handler omits the review payload and local artifact references are not browser resources. A single authorized resource boundary serves both review and branch browsing without serializing every diagram or creating a parallel review system. Server-side freshness and serialized mutation checks prevent stale tabs from approving or commenting on replacement evidence.
  Honors: Requirements 1–4 and 6; exact immutable revisions, SVG safety, semantic identity, existing thread routing and downstream gates, usable plan text during architecture failure..

- `dec_004` · 2026-11-10 · Epic Architect · **Final implementation contracts — publication and recovery**
  Chose Add normal epic/feature publish_architecture_review tool adapters over existing ownership/staging services, backed by durable idempotent intents and a bounded project scheduler. Pin renderer identity, deduplicate jobs, recover from original committed sources, and require explicit retry after bounded recovery. feat_046_001 repairs the strict fixture inventory and proves a real tool-to-HTTP-to-browser journey with restart..
  Rationale: Code inspection found no production caller for the architecture authoring operations. C4ArtifactRenderer.submit starts an in-memory thread per call and staging currently waits for render validation. Durable admission and controlled worker execution close these gaps while preserving existing review, cache and acceptance authorities. The recorded fixture failure is an implementation obligation, not a reason to weaken inventory checks.
  Honors: Normal authorized planning paths, exact baseline and source provenance, bounded offline rendering, no unauthorized dependency installation, release-blocking real-renderer/browser acceptance..

- `dec_005` · 2026-11-10 · Epic Architect · **Final implementation contracts — branch and documentation provenance**
  Chose Pin branch browsing to immutable code/document snapshot descriptors resolved from known session contexts and exact recorded associations. Missing or ambiguous split-repository associations require an explicitly labeled known documentation-ref selection or an unavailable state. Share semantic navigation and lazy verified many-to-many context projections with paired review; keep accepted-lineage references separate..
  Rationale: A current branch and an accepted architecture lineage answer different questions, and tracking HEAD cannot establish a code-to-document association. Snapshot identity and pinned mapping/document reads keep diagrams and context coherent across navigation, branch advance, restart and deep links without introducing branch-wide comments or inferred document coverage.
  Honors: Requirements 5–6; detached HEAD and dirty-edit behavior, split-repository provenance, no one-to-one C4/DESIGN hierarchy, stable citations and ownership mappings, existing serial feature scope..
## Amendment log

_(none)_
