---
id: epic_034
title: Requirements and architecture traceability
tier: epic
status: backlog
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
updated: '2026-11-06'
provider: codex
flex_mode: true
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
13. **Historical coverage.** Populate eligible `DESIGN.md` files and the initial C4 model in the configured documentation destination by replaying every completed, non-cancelled epic, feature, and task, then checking claims against current target code and tests. Every excluded target-code directory names the parent design that covers it. A replay ledger accounts for each work item, including those with no durable design or diagram impact.
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

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

- Define “trivial” and the document boundary. A target-code directory gets a `DESIGN.md` in the configured documentation tree when it owns distinct behavior, state, interfaces, or decisions. Generated files, lifecycle folders such as `docs/tasks/3_completed`, and simple leaf directories are covered by the nearest meaningful parent.
- Give each requirement one home. A parent records system goals, cross-module constraints, and interfaces between children. A child records the requirements and decisions it owns. Parents link to child designs instead of repeating them.
- Make replay evidence based. Use completed, non-cancelled Epic, Feature, and Task records as leads, then check their claims against current code and tests. Mark unresolved gaps; do not present an old plan or unimplemented decision as current behavior.
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

- The C4 model for architecture views and Structurizr DSL for the versioned model. Select and pin local validation/rendering tooling during epic planning.
- The existing plan viewer, plan comments, proposal review, and Git revision paths; extend those surfaces rather than creating a separate approval channel.
- [Epic 36](epic_036_split_target_and_tracking_repos.md) (`depends_on: epic_036`) supplies the optional tracking repository and plan routing before this epic starts. This epic adds design/C4 destination selection on that foundation.

## Feature breakdown

After epic_036 is completed, the Epic Team will create and sequence feature plans here.

## Open questions

- Which Structurizr rendering path best supports local, revision-pinned plan review while keeping the editable DSL in Git?
- For epic and feature proposals, which approved or parent revision is the architecture baseline?
- Should legacy work receive a temporary grace period for missing C4 views while the initial model is backfilled?
- Should the proposed first-release comment scope be reduced to view-level comments with global plan threads as a fallback?

## Decision log

- 2026-11-03 · Human · Brief approved through merge request review.
- 2026-11-06 · Human request · Expand the brief to cover C4/Structurizr architecture and visual proposal review; every diagram change belongs in review, while a change below diagram granularity may simply state no diagram change.
- 2026-11-06 · Human clarification · The side-by-side view compares current and proposed C4 diagrams; interactions in either diagram keep the other at the corresponding architecture context.
- 2026-11-06 · Human sequencing · Complete epic_036 first; then let this epic place design/C4 documentation in the target or tracking repository through `cascade.toml`.
- 2026-11-06 · Human clarification · An epic remains editable after some features merge. Route later feature-plan change requests to the responsible team and escalate cross-feature decisions to the Epic Team; preserve accepted work, add corrective features when needed, and block for human review before any broader restart.

## Amendment log

_(none)_
