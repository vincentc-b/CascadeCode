---
id: epic_004
title: Epic, feature, and task numbering
tier: epic
status: active
parent: null
children:
- feat_009
- feat_010
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-21'
updated: '2026-10-21'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Epic, feature, and task numbering

## Intent

Replace globally sequential work-item identifiers with stable hierarchical identifiers that reveal parentage:

- Epic: `epic_NNN`
- Feature: `feat_NNN_MMM`, where `NNN` is the parent epic number
- Task: `task_NNN_MMM_KKK`, where the first two segments identify the parent feature

Segments are zero-padded to three digits for readable lexical ordering. This epic changes identity and allocation only; titles, lifecycle states, and planning workflow remain unchanged.

### Success criteria

- Every newly created epic, feature, and task receives the canonical hierarchical form.
- Epic numbers remain globally unique; feature numbers are allocated within an epic; task numbers are allocated within a feature.
- Allocation is collision-safe and does not reuse an identifier merely because an item was moved, archived, or deleted.
- New features and tasks created beneath pre-existing epics still derive their hierarchy from the numeric segment of the existing parent ID.
- Every backlog epic and all of its descendant features and tasks are migrated immediately, including board-owned dependencies, citations, parent/child links, paths, and other stored references.
- Active and completed work keeps its existing identifier; those identifiers remain readable and operable during the compatibility period.
- Creation and migration failures do not leave a partially renamed work graph.
- High-signal integration coverage proves creation at all three tiers, sibling numbering in separate parents, compatibility with retained IDs, and backlog-graph migration.

## Macro-architecture

Use one canonical work-ID module for formatting, parsing, validation, and next-child allocation. Creation entry points must ask this module for an ID rather than reconstructing numbering rules.

Allocation reads the relevant namespace: all epics for a new epic, direct features for a new feature, and direct tasks for a new task. It selects the next monotonically increasing segment and commits only if the identifier is still free; concurrent collisions retry through the existing persistence boundary.

Treat backlog migration as a graph rewrite. Build and validate the complete old-to-new mapping first, then rewrite documents, paths, metadata, relationships, dependencies, citations, and board indexes as one recoverable operation. Emit a deterministic dry-run/report so operators can inspect mappings and diagnose conflicts.

Readers accept both retained legacy identifiers and the new hierarchical identifiers. Writers emit only hierarchical identifiers after rollout.

## Cross-module constraints

- Canonical prefixes remain `epic`, `feat`, and `task`; separators are underscores and each numeric segment is three digits.
- IDs are immutable after creation except for the explicit backlog migration in this epic.
- Numeric allocation is based on persisted identity, not list position or title.
- Parentage encoded in a new ID must match the stored parent link; validation rejects disagreement.
- References must be rewritten by structured identity, never by unrestricted text replacement.
- User-authored prose mentioning an old ID is not rewritten unless it is a board-owned structured reference.
- Existing active/completed IDs remain valid inputs; no broad historical renumbering is in scope.
- The migration must be idempotent, detect target collisions before mutation, and produce an audit mapping.
- Tests should concentrate on creation workflows and a representative graph migration; exhaustive unit coverage of trivial format helpers is unnecessary.

## Core dependencies

- Existing board persistence/transaction or recoverable-write mechanism.
- The authoritative indexes and serializers for work metadata and graph relationships.
- All creation interfaces that currently mint epic, feature, or task IDs.

No new external service or datastore is required.

## Feature breakdown

1. **feat_009 — Hierarchical ID allocation for new work**
   - Define the canonical parser/formatter/validator and scoped allocation rules.
   - Integrate all epic, feature, and task creation paths.
   - Preserve read compatibility for retained identifiers.
   - Add creation-level integration coverage, including separate parent namespaces and collision handling.

2. **feat_010 — Backlog epic ID migration** (depends on `feat_009`)
   - Discover backlog epic graphs and generate deterministic old-to-new mappings.
   - Validate collisions and reference coverage before changing state.
   - Rewrite board-owned documents, metadata, paths, indexes, and cross-work references recoverably.
   - Provide dry-run/audit output and representative end-to-end migration coverage.
   - Leave active and completed work untouched.

## Explicit non-goals

- Renumbering active or completed epics and their existing descendants.
- Changing lifecycle states, board ordering, titles, or human-readable slugs.
- Rewriting arbitrary user prose that merely contains an old identifier.
- Introducing configurable segment widths, alternate separators, or a general-purpose ID framework.
- Adding a new external coordination service solely for number allocation.

## Open questions

- Which existing persistence primitive will provide recoverable graph-wide migration semantics? The Epic Architect should select the narrowest mechanism already present in the codebase.
- Do any external integrations persist work IDs outside Cascade's board-owned references? If so, they need an explicit compatibility/notification contract before migration ships.

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-21 · Epic Manager · **Identifier format and allocation**
  Chose Use epic_NNN, feat_NNN_MMM, and task_NNN_MMM_KKK with three-digit underscore-separated segments; allocate child segments monotonically within their direct parent..
  Rationale: The format makes parentage visible, preserves lexical ordering, matches existing canonical prefixes, and limits the change to identity semantics.
  Honors: The human request for hierarchical epic, feature, and task numbering..

- `dec_002` · 2026-10-21 · Epic Manager · **Migration scope**
  Chose Immediately migrate backlog epic graphs and board-owned structured references, while retaining active and completed identifiers as compatible inputs..
  Rationale: This meets the explicit backlog requirement without taking on a high-risk historical rewrite whose product value is low.
  Honors: The success criterion that backlog epics receive hierarchical numbering right away and the frugal-engineering constraint to avoid unnecessary scope..
## Amendment log

_(none)_
