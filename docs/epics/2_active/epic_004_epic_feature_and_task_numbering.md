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
updated: '2026-10-22'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
plan_approved_at: '2026-10-22T04:03:16.999727+00:00'
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

Allocation reads the relevant namespace: all epics for a new epic, direct features for a new feature, and direct tasks for a new task. Within the existing board persistence boundary, each namespace also retains an authoritative high-water mark (or equivalent durable allocation history) so a hard-deleted identifier is never reused. Under the board process lock, allocation chooses one above both the persisted maximum and the high-water mark, then persists the new work item and advanced mark atomically; collision detection remains a defensive retry.

Treat backlog migration as a graph rewrite. Build and validate the complete old-to-new mapping first, then rewrite documents, paths, metadata, relationships, dependencies, citations, and board indexes as one recoverable operation. Emit a deterministic dry-run/report so operators can inspect mappings and diagnose conflicts.

Readers accept both retained legacy identifiers and the new hierarchical identifiers. Writers emit only hierarchical identifiers after rollout.

## Cross-module constraints

- Canonical prefixes remain `epic`, `feat`, and `task`; separators are underscores and each numeric segment is three digits.
- IDs are immutable after creation except for the explicit backlog migration in this epic.
- Numeric allocation is based on persisted identity plus durable allocation history, not list position or title; deleting the highest-numbered item must not lower the namespace high-water mark.
- Parentage encoded in a new ID must match the stored parent link; validation rejects disagreement.
- References must be rewritten by structured identity, never by unrestricted text replacement.
- User-authored prose mentioning an old ID is not rewritten unless it is a board-owned structured reference.
- Existing active/completed IDs remain valid inputs; no broad historical renumbering is in scope.
- The migration must be idempotent, detect target collisions before mutation, initialize or advance every affected namespace's durable high-water mark to at least the greatest assigned segment, and produce an audit mapping.
- Tests should concentrate on creation workflows and a representative graph migration; exhaustive unit coverage of trivial format helpers is unnecessary.

## Core dependencies

- The existing board process lock and Git-backed isolated-index commit boundary, extended narrowly for a prevalidated multi-path graph write with byte-level rollback.
- The authoritative indexes and serializers for work metadata and graph relationships.
- All creation interfaces that currently mint epic, feature, or task IDs.

No new external service or datastore is required.

## Architecture validation

### Recoverable graph-wide writes

The existing primitives are individually insufficient as-is: `write_doc` commits one document and does not restore it after commit failure; `save_doc` restores one path; and the worktree registry's temp-file/`os.replace` transaction applies only to that registry. The narrowest reusable boundary is the existing board `process_lock` plus `commit_paths` isolated-index commit.

The migration implementation must add one board-level graph-write operation that, while holding `process_lock`:

1. computes and validates the full mapping and every rendered destination before mutation;
2. rejects duplicate sources, occupied destinations, invalid parentage, and unresolved structured references;
3. snapshots bytes and existence for every affected board-owned path;
4. writes new files and removes old paths;
5. commits the entire affected path set once through `commit_paths`; and
6. restores the complete snapshot and invalidates board caches if any write or commit fails.

A deterministic manifest records the mapping and affected paths. Re-running after success is a no-op; re-running after a failed attempt starts from the restored pre-migration graph.

### ID persistence outside board documents

Cascade persists work IDs outside plan frontmatter and structured document references in local LangGraph checkpoint filenames/thread IDs, event queues, War Room chat and comment sidecars, the integration-worktree registry and paths, local Git branch names, and commit trailers. For this epic, assume no external integration currently persists Cascade work IDs.

Those local artifacts belong to active execution, while this epic migrates backlog graphs only. Migration therefore does not rename or rewrite runtime artifacts. Before mutation, it must prove the entire selected graph is backlog-only and reject it if any integration-worktree registration, matching local integration branch, checkpoint, or queue/runtime sidecar exists. Board-owned backlog comment/chat sidecars, if present, are included in the structured rewrite and atomic path set. The dry-run report lists every checked local artifact class and any blocker. External-system discovery, migration, and notification are out of scope under the explicit assumption that no external integration currently persists Cascade work IDs; that assumption must be revisited before such an integration is introduced.

## Feature breakdown

1. **feat_009 — Hierarchical ID allocation for new work**
   - Define the canonical parser/formatter/validator, scoped allocation rules, and durable per-namespace high-water marks within the existing board persistence boundary.
   - Integrate all epic, feature, and task creation paths.
   - Preserve read compatibility for retained identifiers.
   - Add creation-level integration coverage, including separate parent namespaces, collision handling, and non-reuse after deletion of the highest allocated item.

2. **feat_010 — Backlog epic ID migration** (depends on `feat_009`)
   - Discover backlog epic graphs and generate deterministic old-to-new mappings.
   - Validate collisions, reference coverage, backlog-only status, and absence of local runtime identity artifacts before changing state.
   - Rewrite board-owned documents, metadata, paths, indexes, cross-work references, applicable board sidecars, and affected durable allocation high-water marks in one locked Git commit with full byte-snapshot rollback.
   - Provide dry-run/audit output and representative end-to-end migration coverage, including injected commit failure and runtime-artifact refusal.
   - Leave active and completed work untouched.

## Explicit non-goals

- Renumbering active or completed epics and their existing descendants.
- Renaming local integration branches, worktrees, checkpoints, or queues.
- Changing lifecycle states, board ordering, titles, or human-readable slugs.
- Rewriting arbitrary user prose that merely contains an old identifier.
- Introducing configurable segment widths, alternate separators, or a general-purpose ID framework.
- Adding a new external coordination service solely for number allocation.

## Open questions

_(none)_

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

- `dec_003` · 2026-10-21 · Epic Manager · **Feature sequencing**
  Chose Deliver canonical allocation and compatibility in feat_009 before the dependent backlog graph migration in feat_010..
  Rationale: Migration needs one settled parser, formatter, and allocation contract; separating it from steady-state creation makes rollout and verification recoverable.
  Honors: The smallest shippable sequence that keeps the system honest..

- `dec_004` · 2026-10-21 · Epic Architect · **Recoverable graph-wide migration**
  Chose Use one board-level graph-write operation under the existing process lock: prevalidate the full mapping, snapshot all affected bytes, mutate paths, commit the complete path set once through commit_paths, and restore the snapshot on any failure..
  Rationale: Existing write_doc and save_doc recovery is document-scoped, while the registry's atomic replacement is registry-specific. Extending the existing lock and isolated-index Git commit boundary is the narrowest mechanism that can make the whole board graph recoverable without adding a datastore or transaction framework.
  Honors: Collision safety, atomic migration, idempotence, and the frugal-engineering preference for the smallest reliable extension..

- `dec_005` · 2026-10-21 · Epic Architect · **Runtime and external ID artifacts**
  Chose Migrate only graphs proven backlog-only and free of runtime or published identity artifacts; reject graphs with worktree registrations, integration branches, checkpoints, queues, or remote review artifacts instead of renaming those systems. Rewrite board-owned backlog sidecars within the atomic migration..
  Rationale: Cascade persists IDs in local execution state and Git/forge identities, but those artifacts arise after dispatch and publication. A strict preflight preserves the approved backlog-only scope and avoids unsafe cross-system renames; retained active and completed IDs remain readable.
  Honors: The explicit compatibility boundary, no partial migration, and the requirement to define an external persistence contract before shipping..

- `dec_006` · 2026-10-21 · Epic Manager · **Architecture validation**
  Chose Assume no external integration currently persists Cascade work IDs; omit remote-system preflight, migration, and notification from this epic while retaining checks for local runtime identity artifacts..
  Rationale: This records the human-confirmed current-state boundary and avoids speculative integration work. Local checkpoints, queues, worktrees, and branches still exist and can make a backlog rename unsafe.
  Honors: In reply to: cmt_001; the human direction to assume no external integrations persist work IDs, plus the approved backlog-only and atomic-migration constraints..

- `dec_007` · 2026-10-22 · Epic Architect · **Allocation history**
  Chose Retain a durable high-water mark (or equivalent allocation history) for each epic, feature, and task namespace, and atomically advance it with creation under the existing board process lock..
  Rationale: Scanning only currently persisted siblings would reuse the highest identifier after hard deletion, contradicting the approved monotonic non-reuse requirement. A small persisted watermark closes that gap without introducing a new service or general transaction system.
  Honors: The epic success criterion that moved, archived, or deleted work IDs are never reused, and the frugal-engineering preference for the smallest reliable persistence extension..
## Amendment log

- 2026-10-22 · Architectural clarification for feat_010 · Required backlog migration to initialize or advance affected durable allocation high-water marks within the same recoverable graph write, preventing reuse of migrated IDs after later deletion.

- 2026-10-22 · Architectural clarification for feat_009 · Required durable per-namespace allocation history and atomic high-water-mark advancement so hard deletion cannot cause ID reuse; added one high-signal deletion/non-reuse integration criterion.

- 2026-10-21 · In reply to: cmt_001 · Adopted the current-state assumption that no external integration persists Cascade work IDs. Removed remote-system preflight and migration requirements while retaining local runtime-artifact refusal and the recoverable graph-write boundary.
