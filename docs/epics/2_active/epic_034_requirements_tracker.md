---
id: epic_034
title: Requirements and architecture traceability
tier: epic
status: active
parent: null
children: []
depends_on:
- epic_036
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-03'
updated: '2026-11-09'
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
# Requirements and architecture traceability

## Intent

Keep functional and non-functional requirements, design choices, and C4 architecture views in version control, with paths that map clearly to the code they describe. Use concise `DESIGN.md` files for meaningful directory boundaries and versioned Structurizr source for the shared architecture model. Epic 36 first establishes optional tracking-repository routing for Cascade plans; this epic adds a `cascade.toml` choice for the design/C4 destination, either with the target code or with the plans. Backfill the current project by replaying completed, non-cancelled epics, features, and tasks against current code and tests.

Make architecture a first-class part of epic and feature proposals. A reviewer should be able to compare the current and proposed C4 diagrams side by side, move through both versions together, and follow the affected requirements and design decisions from the plan. A change entirely inside an existing component may leave the diagrams untouched; the proposal should say so briefly.

An epic remains a living plan while its children are being delivered. A change request after one feature has merged should be assessed against the work already accepted, not restart the epic or discard completed features. The Epic Team owns cross-feature decisions and can add corrective work when a later feature or an accepted feature exposes a gap.

### Success criteria

1. **Design guidance and template.** Provide a design skill, informed by `/home/ubuntu/dev/automatik/skills`, that teaches concise requirements and decisions, document boundaries, C4 view selection, proposal review, and evidence-based updates. Provide a `DESIGN.md` template with a matching table of contents and sections for requirements, decisions and rationale, interfaces, architecture view links, and verification evidence. Parent designs summarize system goals and interfaces; child designs own their detailed requirements without repetition. A design file stored in a tracking repo retains an unambiguous mapping to its target-code directory.
2. **Configurable documentation destination.** Epic 36's `cascade.toml` tracking-repository setting determines where plans live. Add an independent setting in the target repository's `cascade.toml` for `DESIGN.md` files and editable Structurizr DSL: target repository or the configured tracking repository. With no architecture setting, keep documentation in the target repository; selecting the tracking repository requires epic 36's tracking reference. Resolve both destinations consistently for reads, writes, links, reviews, and replay, and report invalid combinations clearly.
3. **Repo-owned architecture model.** Use Git history in the configured design/C4 destination as the source for C4 views. Define stable element, relationship, and view identifiers and clear ownership of shared model fragments. Start with a system context and container view where they are useful; add component, dynamic, or deployment views when they explain a real design choice. Diagrams render from the versioned model; generated images, if used, are reproducible review artifacts rather than independent sources of truth.
4. **Proposal lifecycle.** During epic and feature planning, stage proposed `DESIGN.md` and Structurizr changes on a reviewable branch or patch in their configured repository. Pin the current model separately before approval; do not alter the accepted baseline merely to preview a proposal. The proposed model must be available for review before plan approval or task dispatch. Promote it to current architecture only when the corresponding implementation is accepted, and show stale-baseline/rebase status when the underlying model changes.
5. **Scoped authoring.** Give epic, feature, and task teams the narrowly scoped read, proposal, and update paths needed for their owned requirements and model fragments, including feature-to-epic architecture amendments and closeout edits. Their planning context must include the relevant pinned design and C4 source. Do not grant unrestricted access to other teams' plans or arbitrary repository files.
6. **Traceable proposals.** Epic and feature proposals identify affected requirement IDs and design decisions, link to the relevant `DESIGN.md` sections and C4 views, and state the intended architecture impact. Any proposed architecture change includes its Structurizr model change in the review. If no C4 view changes, a short “no diagram change” note is sufficient. A proposal must not claim an unimplemented design as current behavior.
7. **Paired C4 comparison.** The plan viewer presents the current-state and proposed-state C4 diagrams side by side, clearly labeled with their source repository and revision and the same C4 view or level. Selecting an element or relationship in either diagram focuses and highlights its counterpart in the other. Drilling into a container or component, switching views, and navigating back keeps both sides synchronized. Added or removed elements without a counterpart remain visible and clearly marked on their own side, without forcing the other side to an unrelated target. The proposal text remains available beside or immediately adjacent to the paired diagrams, even when plans and diagrams reside in different repositories.
8. **Requirement and diagram comments.** Reuse the existing epic/feature plan review threads for comments on a requirement ID or a selected C4 view, element, or relationship. Store a semantic anchor with the view/key or requirement ID, current/proposed side, source repository, and revision; route replies to the owning team and retain threads when the source changes. Removed or renamed targets appear as outdated with a path to the source diff. Define how blocking threads affect approval and scoped downstream work. Freehand marks and pixel-positioned annotations are outside the initial release.
9. **Change visibility and review.** Highlight added, removed, and changed elements and relationships across the paired diagrams, with a legend and textual change summary. Every changed view in a proposal is accessible, including views beyond the one initially displayed. Reviewers can trace material diagram changes to requirements and design choices and open the underlying model and plan diff. Compare model semantics rather than treating automatic layout movement as an architecture change. If identifiers or views are renamed, or rendering fails, show a clear mapping or error and the source diff rather than implying the diagrams match. A first-time model has an explicit empty baseline; a proposal with no diagram changes says so clearly.
10. **Revision-bound review.** Epic and feature approval covers the exact plan, requirement-document, and proposed-model revisions shown to the reviewer. Editing any reviewed artifact invalidates the affected sign-offs or approval until it is reviewed again. Open blocking requirement or diagram threads prevent approval or downstream work in their defined scope. A missing or invalid proposed model prevents approval when the proposal claims a diagram change.
11. **Split-repository review.** When plans and architecture live in different repositories, present their changes as one linked review unit with explicit revision pairs. Define merge ordering and a recoverable partial-merge state; neither approval nor dispatch may claim the proposed architecture is accepted when only one side has landed. A later `cascade.toml` destination change must not silently retarget an existing review.
12. **Design review at closure.** Before a Task, Feature, or Epic closes, its team checks affected directory designs, ancestor summaries, and architecture views against the implemented change. The workflow provides an authorized way to propose and merge required documentation and DSL edits. Closure records the accepted update or a short reason none was needed; unresolved material mismatches prevent closure.
13. **Historical coverage.** Populate eligible `DESIGN.md` files and the initial C4 model in the configured documentation destination by replaying every completed, non-cancelled epic, feature, and task, then checking claims against current target code and tests. Every excluded target-code directory names the parent design that covers it. A replay ledger accounts for each work item, including those with no durable design or diagram impact. Also reconcile the target repository's reachable Git history to identify fixes and other commits outside Cascade work records. Use commit messages and, for linked merge requests or pull requests, their descriptions as historical evidence; deduplicate overlapping work-item and commit evidence. Check every inferred claim against current code and tests, and record unavailable review descriptions or ambiguous provenance explicitly.
14. **Reconciliation and validation.** A final pass checks parent–child consistency, cross-directory interfaces, requirement and decision references, view links, table-of-contents headings, Structurizr parse/render results, and claims against current code. Report unresolved gaps explicitly instead of silently accepting stale diagrams or historical plans.
15. **Continue after partial delivery.** An active epic can revise its remaining plan after a child feature merges. Preserve completed feature IDs, commits, review history, decisions, and accepted architecture; do not reset the epic branch or replay completed work. The “current” C4 side for a later proposal is pinned to the latest accepted architecture on the relevant epic integration branch, including merged child work, even if the epic has not yet merged to target trunk.
16. **Route and escalate change requests.** A comment on an active feature first reaches its Feature Team, which replies in the originating thread. A comment on a backlog or otherwise unstaffed feature under an active epic reaches the Epic Team, with the feature and comment context; it must not disappear because that Feature Team has not started. After any sibling has merged, a material feature-plan change request is escalated to the Epic Team for impact triage even if it first appears local. The Feature Team also escalates requests affecting epic constraints, another feature, accepted work, or sequencing. The Epic Team records a decision, and the responsible team posts or relays the outcome in the originating thread. Deliver one accountable handoff rather than silently starting multiple team turns.
17. **Choose the smallest safe revision.** The Epic Team evaluates whether the change belongs in the still-open feature, needs an epic/feature amendment, or warrants a new corrective feature with explicit dependencies on accepted work. A new or materially revised feature receives its own review and human approval; the already merged feature stays accepted. The updated requirements, decisions, and proposed C4 model show the delta from the accepted baseline. A request that cannot be handled safely within the existing epic is surfaced as a visible blocker with a reason and a human decision on replacement or broader replanning; no agent automatically returns the epic to backlog or starts over.
18. **Scope holds and approvals.** While a material request is unresolved, block only affected minting, dispatch, task integration, or feature merge at safe boundaries. If an affected feature already has active tasks, preserve their branches and work, make the hold visible, and require an authorized plan/review decision before resuming. Revision-bound approval is refreshed for changed work, while unrelated completed features and their accepted approvals remain intact. A later corrective feature is never silently covered by the epic's earlier plan approval.

### Acceptance scenarios

- An epic or feature proposal changes a C4 relationship: the current view stays pinned, the proposed view shows the change before approval, a diagram-targeted blocking thread reaches the owning team, and approval waits until it is resolved.
- A reviewer signs off, then a requirement or Structurizr file changes: the prior sign-off no longer authorizes approval or dispatch, and the comparison shows the newly proposed revision.
- Plans and diagrams live in different configured repositories: the viewer shows both repository/revision pairs, and a merge of only one side leaves an actionable pending review rather than a completed architecture update.
- A task changes only code within an existing component: its proposal records no diagram change, and closeout can accept that reason without manufacturing a C4 edit.
- Feature 1 has merged into an active epic, then a reviewer requests a change on feature 2's plan. The request reaches an accountable team even if feature 2 is still in backlog; the Epic Team decides whether to amend feature 2 or add a corrective feature, the reviewer sees that decision in the original thread, and feature 1's merged work remains in the branch and the current C4 baseline.
- Feature 2 is already executing when a blocking change request arrives. Affected task integration pauses without deleting work; after the revised plan and architecture are reviewed, only affected work resumes. A recommendation to restart the epic stays blocked until a human explicitly approves a replacement path.

## Macro-architecture

### Repository and document contract

Extend the existing `RepositoryContext`, project configuration, scoped document tools, plan viewer, comment store, and lifecycle gates. Do not add a second board or approval service. Proposed implementation boundaries are a small shared architecture/document service, adapters in existing epic/feature/task tools, and plan-viewer additions; Feature Teams choose concrete module splits within these contracts.

Use `[architecture] destination = "target" | "tracking"` in the target repository's `cascade.toml`; omission means `target`. Resolve `tracking` only through epic_036's configured tracking repository. Store target-mode directory designs at `<code-directory>/DESIGN.md`. In tracking mode mirror them at `design/<target-repository-key>/<code-directory>/DESIGN.md`, with the root at `design/<target-repository-key>/DESIGN.md`. The repository key is an immutable identity recorded with the mapping, not a basename inferred anew on each load. A mapping index binds each design to its target repository and code-relative directory. Keep the editable workspace and owned fragments at `architecture/<target-repository-key>/` in the selected destination. Preserve and reconcile the existing root design rather than replacing it wholesale.

Each requirement and decision has a stable, unique identifier with one owning design. Parent designs own cross-directory contracts and link to child detail. Each model element and relationship carries a durable semantic ID in its properties; view keys are explicit. Exporter-assigned numeric IDs are local to one artifact and must not be used as cross-revision identity. Require nonempty, workspace-unique semantic IDs for every reviewable element and relationship and unique explicit view keys. Validate ownership and references across the assembled source closure; reject duplicate or missing IDs rather than silently matching labels, array order, or exporter IDs. Derived/implied relationships and repeated dynamic-view occurrences need deterministic identities tied to their explicit source IDs and view/occurrence keys, or a visible unsupported-model error. Rename continuity requires an explicit, reviewed old-to-new mapping; do not infer it from a similar label. A small ownership index maps design directories and model fragments to their editing owner; shared-fragment edits use the owning team's amendment path.

### Model processing and paired review

Use the pinned local Structurizr distribution to validate DSL and export workspace JSON and SVG. The semantic JSON drives comparison and synchronized selection; generated SVG supplies the visual layout. Feature B must prove an adapter from rendered element/relationship nodes to semantic IDs before Feature D relies on it. The Architect's 2026-11-09 offline probe confirmed that the pinned image preserves `cascade.id` properties in JSON but its stock SVG omits those semantic IDs; successful SVG export alone is not evidence of interactive mapping. The adapter must obtain renderer-node-to-exported-model-ID metadata from the trusted rendering pipeline, join it to semantic IDs from the same workspace export, and preserve the verified bindings through sanitization in an artifact manifest or approved SVG attributes. Do not infer bindings from display text, node order, coordinates, or transient SVG IDs. Feature B's first acceptance checkpoint proves element and relationship hit targets across reordered source, identical labels in different containers, parallel relationships, and removed targets. An incomplete or ambiguous mapping blocks interactive review with a source-diff error; it cannot silently select the wrong target. Do not replace required diagram interaction with static screenshots.

The processing boundary materializes only the pinned source closure and explicitly allowed local includes, inside the configured documentation tree at the same revision. Reject path escapes, symlinks out of scope, remote includes/extensions/themes/assets, plugins, scripts, and executable/custom exporters before invoking the parser. No arbitrary project content or exported HTML runs in the plan page. Run the pinned image without network or image pulls, with resource/time limits and isolated output; sanitize rendered SVG and serve only approved local viewer assets. Rendering is a background artifact operation, not code execution on a browser page request. Cache keys include source closure, tool digest, and renderer settings.

The paired view uses one state containing view key/level, selected semantic target, and navigation history. Each side resolves that state independently against its pinned model. Missing counterparts have an explicit absent state while the changed object remains visible on its own side. Enumerate the union of changed views. Semantic comparisons cover model properties, relationships, containment, and view membership; layout coordinates and automatic routing are not architecture changes. A parse/render/mapping failure shows an error and source diff, and cannot be presented as matching diagrams.

### Revision-bound proposal and acceptance

A review unit records owner work ID, target repository identity, fixed documentation destination, plan repository/path/revision, design paths and revisions, accepted baseline model revision, proposed model revision, source-closure digest, impacted requirement/decision IDs, affected work IDs, tool digest, and architecture impact (`changed` or justified `no_diagram_change`). An initial model uses an explicit empty baseline. Even a no-diagram-change proposal binds its design changes and reason to the reviewed revision.

For the first epic proposal, current means the last accepted model reachable from the epic's starting target revision, or an explicit empty model. After accepted child delivery, current means the latest accepted architecture on that epic integration lineage, including merged children. A feature pins that accepted epic baseline when its proposal is prepared. Planning-only ancestor proposals are never mislabeled as accepted. If a feature requires an unaccepted predecessor's architecture, record the dependency and stage it as proposed context; refresh against the predecessor's accepted result before affected dispatch.

Use explicit review states: draft, reviewable, approved, implementing, acceptance_pending, accepted; invalidated or stale states retain prior evidence and identify the required review/rebase action. Pin proposals on owned review branches or immutable patches before approval. Any edit to a bound artifact invalidates affected sign-offs and approval. Recheck revisions, baseline freshness, blocking threads, and affected scope under existing lifecycle locks at approval, dispatch, integration, merge, and closeout boundaries. A changed model that cannot validate/render cannot become reviewable. Revalidation alone does not substitute for human review of a changed proposal.

In a single repository, merge code and corresponding accepted documentation together where possible. With split repositories, persist a linked review unit and promotion journal before either merge. Merge the normally approved implementation into the owned integration branch first, then the exact reviewed documentation change into its configured destination, and only then advance the accepted architecture pointer and finalize completion. Either half alone is `acceptance_pending`: retain both refs, show the missing operation, and hold dependent dispatch/integration. Retry only the missing side idempotently; conflicts or changed revision pairs require re-review. Do not roll back accepted unrelated work or pretend Git provides a cross-repository transaction. A destination configuration edit cannot retarget an existing review; migration is an explicit new reviewed operation.

Key the promotion journal by review-unit identity and the exact approved revision tuple, with expected destination heads, accepted-baseline generation, and observed merge results. Accepted architecture pointers belong to an integration lineage, not one mutable project-wide pointer: accepting a feature into an epic does not advance target-trunk architecture. Reserve promotion and compare expected heads/generation under the owning lifecycle lock; after Git operations, recheck those expectations before finalizing. A restart inspects recorded refs and ancestry to recognize an already landed side. A competing promotion or changed merge result becomes stale/pending for re-review rather than overwriting a newer accepted baseline. Avoid holding a lifecycle lock throughout rendering or remote Git operations.

### Semantic comments and material change requests

Extend existing epic/feature threads with typed anchors: requirement, view, element, relationship. Bind the anchor to semantic ID/view key, current/proposed side, repository, and revision, independent of Markdown heading slugs. Preserve threads and source-diff links after revisions; missing or explicitly renamed anchors become outdated until reviewed/reanchored. An outdated blocking thread remains blocking until the authorized human resolves it.

Blocking scope is the owning proposal plus explicit affected work IDs and dependents, inferred from requirement/model ownership and proposal citations. If the owner cannot establish a safe narrower scope, hold the owning proposal's subtree and surface that reason; never silently broaden a local thread to unrelated epics. Enforce holds at minting, dispatch, task integration, feature merge, and closeout safe boundaries. Running tasks may retain and finish their branches, but held results cannot integrate.

Deliver a feature comment once to the live Feature Team, or to the Epic Team when the feature is backlog/unstaffed. Durable handoff identity includes originating comment, feature, affected work, and receiving owner. Following any accepted sibling merge, material feature-plan changes require Epic Team impact triage even if initially local. The decision chooses amendment of remaining work, a separately approved corrective feature, or a visible human decision on replacement. Preserve accepted feature IDs, commits, decisions, review history, and architecture. Reply or relay the outcome in the originating thread; do not resolve it on the human's behalf.

### Authoring, closure, and historical reconstruction

Planning context contains the relevant pinned ancestor/owned designs and model fragments. Scoped tools authorize reads and staged proposals by ownership, including feature-to-epic amendments and Task closeout changes; parent summaries and shared fragments require their owners. Grant a bounded historical replay reader for completed, non-cancelled records and associated Git/review evidence, rather than giving all teams arbitrary board access.

At every closure tier, record the inspected change and design/model revisions, affected designs and ancestors, and either the accepted documentation update or a short justified no-change result. Material mismatches block closure. For split repositories, a pending promotion cannot satisfy this receipt.

Replay uses a pinned inventory of completed non-cancelled work records and target Git history reachable from the agreed current baseline. Account for implementation and fix commits outside Cascade records, including direct commits, merges and available squash/rebase provenance; consult linked MR/PR descriptions through existing authorized forge access. Do not require one MR per commit or count the same evidence twice. Unreachable/deleted history and unavailable review bodies are explicit coverage limitations, not invented evidence. Cancelled plans are excluded as requirements sources, but surviving code is still checked against actual implementation and reachable commits.

Assign one owner per directory and shared fragment, reconcile leaves to root, then validate downward and across interfaces. The ledger records each work item and uncovered commit, relevant MR/PR references, evidence revisions, affected requirement/decision IDs, outcome (durable impact, superseded, no durable impact, or unresolved), and excluded-directory coverage. Commit/MR narratives are leads, not proof of current behavior. Reconcile new accepted work since the inventory pin before final closeout.

### Delivery validation

Prefer a few high-signal integration and browser scenarios over broad mock-based unit coverage:

- Config defaults and target/tracking routing; invalid tracking selection; stable mappings after a destination edit.
- Real pinned-tool DSL/JSON/SVG processing and verified node bindings; missing/duplicate semantic IDs, reordered source, identical labels, parallel relationships, stable-ID semantic diffs, layout-only changes, first model, removed targets, parse failure, and rejected executable/escaping source.
- Review then mutate each artifact type; stale-baseline rebase; exact revision gates; crash/retry after either split merge without duplicate acceptance; competing promotions cannot overwrite another integration lineage or a newer accepted baseline.
- Paired element and relationship focus, drill/view/back navigation in both directions, all changed views, added/removed states, and accessible text/diff fallback.
- Anchored comments on requirement/view/element/relationship; outdated targets; active versus unstaffed routing; one accountable escalation; scoped holds with active tasks and an already merged sibling.
- Closeout mismatch/no-change receipts and replay ledger reconciliation, including a direct fix commit, an MR-described change without a work item, superseded/cancelled work, and unavailable review provenance.

## Cross-module constraints

- Define “trivial” and the document boundary. A target-code directory gets a `DESIGN.md` in the configured documentation tree when it owns distinct behavior, state, interfaces, or decisions. Generated files, lifecycle folders such as `docs/tasks/3_completed`, and simple leaf directories are covered by the nearest meaningful parent.
- Give each requirement one home. A parent records system goals, cross-module constraints, and interfaces between children. A child records the requirements and decisions it owns. Parents link to child designs instead of repeating them.
- Make replay evidence based. Use completed, non-cancelled Epic, Feature, and Task records, uncovered target-code commits, and linked MR/PR descriptions as leads, then check their claims against current code and tests. Account for fixes outside Cascade, deduplicate overlapping evidence, and name inaccessible history or review descriptions. Mark unresolved gaps; do not present an old plan, commit narrative, or unimplemented decision as current behavior.
- Preserve the existing root `DESIGN.md`. Reconcile or migrate it into the configured design-document destination through focused, reviewable edits. Keep work-item history in the work-item records rather than copying it into design docs.
- Keep documents concise and durable. Record functional and non-functional requirements, key decisions and rationale, interfaces, and important flows. Use Structurizr C4 views for architecture; retain small Mermaid diagrams for flows or state changes when they add clarity. Avoid task plans and line-by-line code descriptions.
- Keep the architecture model independent of a hosted Structurizr account. A checkout and documented local tooling must be enough to validate and render the committed views for review.
- Compare explicit revisions from the same proposal, not whichever worktree happens to be current at page load. Preserve the existing plan comment and human approval boundaries while adding diagram review.
- Treat an escalation as an explicit cross-team event with the originating comment, affected work IDs, and owning team. Preserve the in-thread reply and link to the Epic Team's visible decision; never rely on an implicit comment fan-out.
- Preserve accepted child commits and review lineage when revising an active epic. A changed dependency or architecture baseline may require rebase and re-review of pending work, but not destructive reset of completed siblings.
- Resolve plan, design-doc, and C4 references through the destinations configured in the target repo's `cascade.toml`; retain source-repository and revision provenance across repository boundaries.
- Keep requirement and C4 comment targets distinct from Markdown heading slugs so existing section-based blocking behavior does not silently give a diagram thread the wrong scope.
- Render versioned architecture source through a controlled local path, including a defined policy for DSL includes and scripts; a browser view of a proposal must not execute arbitrary project content.
- Treat a diagram as an abstraction of the architecture, not a map of every function. A code change with no material C4 impact needs a short note, not a contrived diagram edit.
- Specify concurrent ownership. Give each directory design one editing owner during replay, with a review of shared interfaces and ancestor summaries before merging changes.

## Core dependencies

- C4 views use Structurizr DSL and the existing `structurizr/structurizr:2026.09.19-playwright` image pinned to `sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`. The canonical dependency manifest declares the host runner and exact no-install verification recipe. A planning smoke on 2026-11-09 successfully validated DSL, exported JSON, and rendered SVG with image pulls and networking disabled. This is advisory evidence; it does not replace Cascade's canonical dependency check.
- Tool sources: [Structurizr binaries](https://docs.structurizr.com/binaries) documents the pinned distribution family; [export commands](https://docs.structurizr.com/export) documents JSON/SVG export. Reuse the installed Docker/runtime and repository Python/JavaScript test tools. No hosted Structurizr account, new UI framework, or dependency installation is authorized by this plan.
- Dependency readiness currently requires `run_dependency_check` for `dep_structurizr` against manifest revision 1. The Epic Team's exposed tools can declare dependencies but cannot run or attest the canonical check; the existing dependency-check workflow must record it before feature minting and plan sign-off. No `none_required` workaround or fabricated evidence.
- The existing plan viewer, plan comments, proposal review, and Git revision paths; extend those surfaces rather than creating a separate approval channel.
- [Epic 36](epic_036_split_target_and_tracking_repos.md) (`depends_on: epic_036`) supplies the optional tracking repository and plan routing before this epic starts. This epic adds design/C4 destination selection on that foundation.

## Feature breakdown

The following seven bounded slices cover all success criteria. These are planning keys, not minted feature IDs. After canonical software readiness passes, mint them in this order with the listed dependency edges and preserve this scope in their feature specs. Human plan approval remains the dispatch boundary.

| Key | Feature | Depends on | Owned result and acceptance coverage |
| --- | --- | --- | --- |
| A | Design guidance and configurable documentation destinations | epic_036 complete | Design skill/template informed by automatik; target/tracking resolver and stable code-directory mapping; root preservation; one-home requirements and ownership. Criteria 1–2 and document-boundary constraints. |
| B | Versioned C4 model and controlled local rendering | A | Stable IDs/view keys, fragment ownership, pinned source closure, DSL validation and JSON/SVG pipeline, semantic diff and render-node mapping proof. Criteria 3, 9 and controlled execution. |
| C | Revision-bound architecture proposals and recoverable acceptance | A, B | Review-unit schema, pinned accepted/proposed revisions, stale status, approval/dispatch checks, minimum owner-scoped proposal staging, single/split repository acceptance journal and lineage/concurrency checks. Criteria 4, 6, 10–11 and baseline portion of 15. |
| D | Paired C4 review and semantic comment threads | B, C | Synchronized comparisons and all changed views; requirement/view/element/relationship anchors; semantic change summaries; outdated targets; approval and downstream scope gates using existing threads. Criteria 7–10. |
| E | Living epic revisions and accountable change-request routing | C, D | Active/unstaffed comment routing, one accountable escalation, Epic impact triage, scoped holds, separately reviewed corrective work, preserved accepted siblings. Criteria 15–18. |
| F | Scoped design authoring and closure reconciliation | A, C, D | Pinned planning context, narrow write/proposal capabilities, ancestor/shared-fragment amendments, bounded replay evidence access, closure receipts and material-mismatch gates at all tiers. Criteria 5 and 12. |
| G | Historical design reconstruction and final validation | B, E, F | Completed-work plus uncovered-commit/MR inventory; exclusive directory ownership; evidence-backed designs and initial model; complete replay/exclusion ledger; final consistency/render/revision checks. Criteria 13–14 and final end-to-end acceptance. |

Feature C must deliver the minimum authorized staging/read/review path together with its gates, so a newly required proposal is actually authorable without waiting for F. F extends that path to full tier-specific context, ancestor/shared-fragment amendments, replay access, and closure. Gate enablement is explicit and versioned; already executing work keeps its recorded rollout state, while new or materially revised proposals after enablement must bind the required artifacts and receive review. No rollout exception permits a claimed diagram change with a missing model. E and F may proceed independently after their dependencies, subject to shared-file ownership. G reconciles accepted delivery through the final inventory cut. Each feature includes its relevant automated acceptance scenarios and documentation closeout; do not defer all integration tests to G.

First release excludes freehand/pixel annotations, hosted architecture services, a general-purpose diagram editor, automatic rename inference, full support for executable DSL, and exhaustive function-level diagrams. It retains all semantic comment target types, split-repository recovery, and post-merge change handling required by the brief.

## Open questions

The product choices are specified above: pinned local Structurizr processing; latest accepted epic integration architecture as the later-proposal baseline; and all four semantic comment target types.

Legacy records remain readable and are not retroactively reopened. Missing architecture is an explicit empty/unmodeled state. New or materially revised proposals after the workflow is enabled must satisfy the new gates; no grace period may authorize a claimed but missing diagram change. Replay fills historical coverage and records unresolved gaps.

Architect review completed on 2026-11-09 against the repository context, comment schema, approval/sign-off gates, and pinned renderer. The review strengthened semantic-ID validation and SVG binding acceptance, integration-lineage promotion/recovery, and the minimum authoring path required when gates become active. The renderer probe is advisory; implementation of the mapping adapter remains Feature B's first acceptance checkpoint.

Pending planning work: canonical `run_dependency_check` for `dep_structurizr` (the current Epic Team tool registry exposes manifest authoring but no check execution); then feature minting, Epic Manager review of these changes, and both roles' sign-off on the final revision. Architect sign-off is not yet recorded because canonical dependency readiness is still `missing_check`. These are readiness actions, not permission to omit acceptance criteria.

## Decision log

- 2026-11-03 · Human · Brief approved through merge request review.
- 2026-11-06 · Human request · Expand the brief to cover C4/Structurizr architecture and visual proposal review; every diagram change belongs in review, while a change below diagram granularity may simply state no diagram change.
- 2026-11-06 · Human clarification · The side-by-side view compares current and proposed C4 diagrams; interactions in either diagram keep the other at the corresponding architecture context.
- 2026-11-06 · Human sequencing · Complete epic_036 first; then let this epic place design/C4 documentation in the target or tracking repository through `cascade.toml`.
- 2026-11-06 · Human clarification · An epic remains editable after some features merge. Route later feature-plan change requests to the responsible team and escalate cross-feature decisions to the Epic Team; preserve accepted work, add corrective features when needed, and block for human review before any broader restart.

- `dec_001` · 2026-11-09 · Epic Manager · **Historical coverage**
  Chose Include uncovered target Git commits and linked MR/PR descriptions in design replay. In reply to: cmt_001..
  Rationale: Completed Cascade records omit direct fixes and other changes. Reconcile pinned Git history with work records, deduplicate evidence, verify narratives against current code/tests, and explicitly ledger missing review provenance.
  Honors: Success criteria 13–14; human comment cmt_001; evidence-based design without historical plans becoming current truth..

- `dec_002` · 2026-11-09 · Epic Manager · **Feature breakdown**
  Chose Deliver seven bounded slices A–G; retain requirement, view, element, and relationship comments, split-repository acceptance recovery, and living-epic revision controls..
  Rationale: The brief requires these capabilities. Scope economy comes from reusing existing board, viewer, comments, approvals, and lifecycle gates; defer freehand annotations, hosted services, diagram editing, and automatic rename inference. Mint only after canonical dependency readiness.
  Honors: All 18 success criteria; frugal engineering; existing human approval and scoped-authority boundaries..

- `dec_003` · 2026-11-09 · Epic Manager · **Proposal lifecycle**
  Chose Pin later proposals to the latest accepted architecture on the epic integration lineage; preserve completed children and represent split merges as acceptance_pending until both reviewed sides land..
  Rationale: An accepted child changes the real baseline before the epic reaches trunk. Pending proposal edits cannot advance current architecture. Exact revision binding and scoped holds prevent stale approvals from covering changed or corrective work.
  Honors: Success criteria 4, 10–11 and 15–18; preserve accepted commits and review lineage..

- `dec_004` · 2026-11-09 · Epic Manager · **Core dependencies**
  Chose Declare the existing Structurizr 2026.09.19-playwright image by immutable digest; use offline DSL validation, semantic JSON, and SVG; require canonical verification before minting/sign-off..
  Rationale: The installed image passed advisory validate/JSON/SVG smoke checks without downloads. Reusing it avoids a host Java upgrade or new renderer dependency. The smoke is not canonical readiness evidence; manifest revision 1 still requires run_dependency_check.
  Honors: Local reproducible architecture tooling; no dependency installation without explicit authorization; no bypass of the software readiness gate..

- `dec_005` · 2026-11-09 · Epic Architect · **Model processing and paired review**
  Chose Require validated semantic IDs and a renderer-to-model binding artifact; make its proof Feature B's first acceptance checkpoint..
  Rationale: The pinned offline probe passed DSL validation and JSON/SVG export, but semantic properties survived only in JSON. Stock SVG cannot alone provide reliable paired selection. Bind renderer metadata to the same export, preserve it through sanitization, and test repeated labels, source reordering, and parallel relationships; fail visibly for ambiguous mappings.
  Honors: Success criteria 3, 7–10; reproducible local rendering and meaningful integration evidence without label/order heuristics..

- `dec_006` · 2026-11-09 · Epic Architect · **Revision-bound proposal and acceptance**
  Chose Bind promotion journals to exact approved revision tuples and expected heads; scope accepted architecture pointers to integration lineages..
  Rationale: An accepted child must advance its epic baseline without claiming target trunk has changed. Concurrent promotions and crashes must recheck recorded heads, generation, and merge results, resume only the missing operation, and never overwrite newer accepted architecture.
  Honors: Success criteria 4, 10–11 and 15; recoverable split-repository acceptance and preservation of accepted siblings..
## Amendment log

_(none)_
