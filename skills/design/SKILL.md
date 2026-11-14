---
name: design
description: Author and review C4 architecture and implementation diagrams in hierarchical DESIGN.md files, with source links, lifecycle coverage, and one owner per requirement and decision.
---

# Design documentation

Use this skill when creating, updating, or reviewing repository design documents. Start from [templates/DESIGN.md](templates/DESIGN.md) unless the repository already has a compatible format.

## Choose document boundaries

- A meaningful code directory owns a `DESIGN.md` when it has distinct behavior, state, interfaces, or decisions that would make a parent summary misleading.
- A trivial directory stays in its nearest meaningful parent's design. Name it there when the coverage would otherwise be ambiguous.
- Generated, vendored, cache, build-output, and lifecycle-only directories do not own designs. Name their covering parent; do not document generated contents as architecture.
- Respect Git ignore rules and exclude hidden directories when discovering candidates.

## Keep one owner

- Give every durable requirement and decision a stable identifier scoped to its owning design, for example `REQ-ROOT-001` or `DEC-QUEUE-002`.
- Record a requirement or decision in exactly one design. Other designs link to its identifier and add only local implications.
- Root and parent designs own system goals, cross-cutting constraints, shared contracts, and interfaces between children.
- Child designs own requirements and decisions local to their directory. A parent summarizes the boundary and links to the child instead of copying its detail.
- When moving ownership, update all references in the same change. Never leave two apparent homes.

## Reconcile existing documents

1. Read the existing design, relevant parent and child designs, current code, and the scoped diff.
2. Preserve accurate prose, diagrams, identifiers, and rationale. Make focused edits for missing or stale facts instead of rewriting the document to match the template mechanically.
3. For a full-tree request, work from meaningful leaves to the root, then verify downward and across sibling interfaces. For a diff-scoped request, update changed directories, their design-owning ancestors, and affected interface consumers only.
4. Keep work history, task plans, and implementation narration in work records. Designs describe durable current behavior as matter-of-fact statements. Do not mention epics, feature/task history, previous requirements, migrations from earlier designs, or implementation chronology. Explain current constraints and rationale without narrating how the design evolved.

## Content contract

Keep the template's table of contents and headings aligned. A design records:

- functional and non-functional requirements with one owning ID;
- decisions with alternatives or constraints considered and a concise rationale;
- public and cross-directory interfaces, including failure behavior;
- important flows that are clearer as a small diagram;
- links to authoritative architecture source and rendered views, or an explicit statement that no separate model is authoritative;
- verification evidence tied to requirements, such as test paths, scenarios, review revisions, or a justified gap;
- child-design links and named coverage for trivial or generated directories.

Use C4 views for non-trivial architecture and small Mermaid diagrams for focused flows or state changes. Architecture links must resolve from the checkout and must not depend on a hosted account. Do not invent a diagram change when a code change is below the model's abstraction level; record the justified no-change result in the work closeout instead.

## Verification

Before finishing, check that:

- each requirement and decision has one owner and every cross-reference resolves;
- parent summaries agree with child detail without duplicating it;
- interfaces agree on both sides of each boundary;
- every meaningful directory owns a design and every skipped directory has a clear covering parent;
- architecture links and verification evidence exist and describe current, inspectable artifacts;
- the document contains no task plan, speculative implementation detail, or stale generated inventory.

## Implementation depth and team responsibilities

A reader must be able to follow a significant subsystem from the system/context
view through its container/component boundary to its implementation and lifecycle.
A box named "teams", "runtime", or "service" is not sufficient detail for a
subsystem with distinct roles, persistent state, or recovery behavior.

For each affected significant subsystem:
- Show its collaborating implementation modules or types in the owning design,
  with checkout-relative links to real files and entry-point symbols.
- Diagram the principal execution sequence or state transitions. Explain inputs,
  outputs, persistent state, restart/resume behavior, and important failure gates.
- Link the parent C4 view to the owning design and link the design back to the
  model and relevant view keys. Use focused views to keep diagrams readable.
- Keep stable semantic IDs and the source contract in sync with C4 edits.
  Use only view types supported by the repository validator. Code-level and
  behavioral Mermaid diagrams in DESIGN.md complement static C4; do not pretend
  implementation modules are separately deployed containers.
- Do not inventory every class or require diagrams for trivial helpers. An
  unchanged model is acceptable only when existing views still explain the
  changed behavior; record the concrete reason in closeout.

Planning managers and architects establish boundaries, diagrams, ownership and
implementation coverage before plan sign-off. SWE updates diagrams and links
against the implemented code, including deviations from the plan. Reviewers and
Boss check coverage and evidence before recommending completion; they must not
claim completeness from the mere presence of a model or a successful render.
Unresolved material gaps must be explicit and routed to the owning team.

Verification includes source-contract validation, supported local rendering when
available, resolving source/design links, and tracing one normal and one
failure/resume scenario against code. Record actual checks and limitations in the
work record. Changes must not silently rewrite accepted snapshots or bypass the
repository's revision-pinned architecture publication workflow.
