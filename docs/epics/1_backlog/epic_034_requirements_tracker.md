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

### Success criteria

1. **Design guidance and template.** Provide a design skill, informed by `/home/ubuntu/dev/automatik/skills`, that teaches concise requirements and decisions, document boundaries, C4 view selection, proposal review, and evidence-based updates. Provide a `DESIGN.md` template with a matching table of contents and sections for requirements, decisions and rationale, interfaces, architecture view links, and verification evidence. Parent designs summarize system goals and interfaces; child designs own their detailed requirements without repetition. A design file stored in a tracking repo retains an unambiguous mapping to its target-code directory.
2. **Configurable documentation destination.** Epic 36's `cascade.toml` tracking-repository setting determines where plans live. Add an independent setting in the target repository's `cascade.toml` for `DESIGN.md` files and editable Structurizr DSL: target repository or the configured tracking repository. With no architecture setting, keep documentation in the target repository; selecting the tracking repository requires epic 36's tracking reference. Resolve both destinations consistently for reads, writes, links, reviews, and replay, and report invalid combinations clearly.
3. **Repo-owned architecture model.** Use Git history in the configured design/C4 destination as the source for C4 views. Define stable element, relationship, and view identifiers and clear ownership of shared model fragments. Start with a system context and container view where they are useful; add component, dynamic, or deployment views when they explain a real design choice. Diagrams render from the versioned model; generated images, if used, are reproducible review artifacts rather than independent sources of truth.
4. **Traceable proposals.** Epic and feature proposals identify affected requirement IDs and design decisions, link to the relevant `DESIGN.md` sections and C4 views, and state the intended architecture impact. Any proposed architecture change includes its Structurizr model change in the same review. If no C4 view changes, a short “no diagram change” note is sufficient. A proposal must not claim an unimplemented design as current behavior.
5. **Paired C4 comparison.** The plan viewer presents the current-state and proposed-state C4 diagrams side by side, clearly labeled with their source repository and revision and the same C4 view or level. Selecting an element or relationship in either diagram focuses and highlights its counterpart in the other. Drilling into a container or component, switching views, and navigating back keeps both sides synchronized. Added or removed elements without a counterpart remain visible and clearly marked on their own side, without forcing the other side to an unrelated target. The proposal text remains available beside or immediately adjacent to the paired diagrams, even when plans and diagrams reside in different repositories.
6. **Change visibility and review.** Highlight added, removed, and changed elements and relationships across the paired diagrams, with a legend and textual change summary. Every changed view in a proposal is accessible, including views beyond the one initially displayed. Reviewers can trace material diagram changes to requirements and design choices, comment through the existing review path, and open the underlying model and plan diff. If identifiers or views are renamed, or rendering fails, show a clear mapping or error and the source diff rather than implying the diagrams match. A first-time model has an explicit empty baseline; a proposal with no diagram changes says so clearly.
7. **Design review at closure.** Before a Task, Feature, or Epic closes, its team checks affected directory designs, ancestor summaries, and architecture views against the implemented change. The workflow provides an authorized way to propose and merge required documentation and DSL edits. Closure records the accepted update or a short reason none was needed; unresolved material mismatches prevent closure.
8. **Historical coverage.** Populate eligible `DESIGN.md` files and the initial C4 model in the configured documentation destination by replaying every completed, non-cancelled epic, feature, and task, then checking claims against current target code and tests. Every excluded target-code directory names the parent design that covers it. A replay ledger accounts for each work item, including those with no durable design or diagram impact.
9. **Reconciliation and validation.** A final pass checks parent–child consistency, cross-directory interfaces, requirement and decision references, view links, table-of-contents headings, Structurizr parse/render results, and claims against current code. Report unresolved gaps explicitly instead of silently accepting stale diagrams or historical plans.

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
- Resolve plan, design-doc, and C4 references through the destinations configured in the target repo's `cascade.toml`; retain source-repository and revision provenance across repository boundaries.
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
- Should a missing or invalid required view block epic/feature approval, or surface as an explicit warning until the initial model is established?

## Decision log

- 2026-11-03 · Human · Brief approved through merge request review.
- 2026-11-06 · Human request · Expand the brief to cover C4/Structurizr architecture and visual proposal review; every diagram change belongs in review, while a change below diagram granularity may simply state no diagram change.
- 2026-11-06 · Human clarification · The side-by-side view compares current and proposed C4 diagrams; interactions in either diagram keep the other at the corresponding architecture context.
- 2026-11-06 · Human sequencing · Complete epic_036 first; then let this epic place design/C4 documentation in the target or tracking repository through `cascade.toml`.

## Amendment log

_(none)_
