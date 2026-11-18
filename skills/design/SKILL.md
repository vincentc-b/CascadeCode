---
name: design
description: Author and review C4 architecture and implementation diagrams in hierarchical DESIGN.md files, with source links, lifecycle coverage, and one owner per requirement and decision.
---

# Design documentation

Use this skill when creating, updating, or reviewing repository design documents. Start from [templates/DESIGN.md](templates/DESIGN.md) unless the repository already has a compatible format.

## Document contract and first use

| Document | Owns | Does not own |
|---|---|---|
| `README.md` | Installation, configuration, first use, routine operation, and links to deeper documentation. | Detailed architecture or delivery history. |
| Root and child `DESIGN.md` | Current requirements, architecture, interfaces, durable choices and rationale, and inspectable verification references. | Delivery IDs, schedules, status reports, chronology, or a backlog. |
| Epic / feature / task records | Scope, parent/child IDs, dependencies, acceptance criteria, proposed changes, revisions, decision history, execution evidence, and closeout. | A second authoritative copy of current architecture. |

For a new repository, read its brief and existing documentation before creating
the root design from the template. Document the system that exists; do not claim
planned components or unrun checks are implemented or verified. Keep proposed
behavior and sequencing in work records. A design proposal on a work branch must
be reviewed as a proposal and reconciled with the code before completion.
Create child designs as meaningful boundaries emerge, not for empty scaffolding.
Respect configured target/tracking documentation destinations and existing
formats; initialization installs the template, not a fictional project design.

Link from work records to stable design requirement/decision IDs. Design IDs
must describe their owning subsystem, not encode an epic, feature, task, or date.
Keep historical attribution in the work record when promoting a durable decision
into its owning design. Product-domain terms and illustrative IDs needed to
explain a schema or API are allowed; they must not attribute architecture to a
particular delivery.

For example, replace "Epic 044 added lazy imports after the startup incident"
with "Repository-context dependencies are imported lazily to avoid initialization
cycles." Preserve the incident and its delivery evidence in the work record.

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
4. Keep work history, task plans, and implementation narration in work records. Designs describe durable current behavior as matter-of-fact statements. Do not include epic/feature/task IDs as attribution, delivery history, previous requirements, migrations from earlier designs, or implementation chronology. Explain current constraints and rationale without narrating how the design evolved. Domain concepts and schema examples remain valid under the document contract above.

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

## Review and closeout

Apply this check before plan sign-off/publication and again before task delivery
or feature/epic completion, including documentation-only changes:

1. Read the changed designs and affected parent/child interfaces against the
   final diff. Reconcile requirements, decisions, diagrams and evidence; remove
   superseded statements instead of appending a history of changes.
2. Review prose, headings, tables and diagram labels for delivery IDs, dates used
   as change history, "previously", "introduced in", and similar attribution.
   Judge context: protocol dates, compatibility constraints, domain concepts and
   schema examples can be current design facts. Rewrite historical narration
   into the current rule and its rationale, keeping useful history in work records.
3. Record the designs reviewed, updates made (or a concrete no-change reason),
   verification performed and unresolved gaps in the work closeout. Do not put
   this review log in `DESIGN.md`.
4. Fix violations before sign-off or recommending completion. If ownership or
   scope prevents the edit, route the specific gap to the owning team and report
   it explicitly rather than claiming documentation is complete.

These are semantic review requirements, not a blanket text ban on IDs or dates.

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
  Use only view types supported by the repository validator. For significant
  components in this Structurizr model, provide a native custom code view with
  `cascade.codeComponent` naming the component semantic ID. Its custom code
  elements use `cascade.parent`, `cascade.sourcePath`, and `cascade.sourceSymbol`
  to identify real implementation and its owning component. Keep model and
  contract declarations synchronized. Verify Explore reaches Code and Level up
  returns to the component view; a document link alone does not satisfy this.
  Behavioral Mermaid diagrams in DESIGN.md can supplement the integrated view.
  Do not pretend implementation modules are separately deployed containers.
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

## Required depth and change-impact review

For architecture-affecting work, include a diagram-impact inventory in the plan
and reconcile it against the implemented diff at closeout. Record each affected
view key, owning design, source symbols, required update and verification result.
Check all levels below; an unchanged level needs a concrete reason grounded in
the diff, not a blanket "no architecture impact" claim.

| Level | What readers must be able to understand |
|---|---|
| Landscape / system context | People, systems, external dependencies and responsibility boundaries. |
| Containers | Runtime/data boundaries, communication and persistence; do not imply OS isolation from a C4 container. |
| Components | Significant responsibilities, collaborators, public interfaces and the owner of each code view. |
| Code | Real implementation functions/types/modules, their relationships and entry points, framework/library use, state/checkpoint ownership, tool/provider wiring and enforceable isolation boundaries. Use focused views of significant components, not exhaustive class inventories. |
| Supplementary behavior | Normal execution, state transitions, failure/recovery and restart/resume where static relationships alone cannot explain the subsystem. Keep these diagrams in the owning design and link them from the architecture documentation. |

Epic planners assign ownership and budget work for affected levels, including
Code; Feature planners make those updates part of Task acceptance criteria.
Task implementers reconcile the model, source contract, code views and owning
designs with actual code. Reviewers and Boss verify the inventory before
recommending completion. If required edits exceed a Task's authorized scope,
report the gap to its owning team rather than silently omitting it or bypassing
guards.

For Structurizr code views, verify an actual UI path from context through
container and component to Code, Level up and deep-link restoration, and opening
the pinned source for representative code nodes. Validate both normal and
failure/isolation behavior against source. Test renamed/deleted symbols and
changed component ownership for stale links. Verify warm navigation reuses
artifacts and new views do not introduce per-view process startup or remove
render bounds. Report measured performance as evidence, not a universal latency
promise.

A successful render alone is insufficient: disconnected code views, stale source
symbols, documentation-only substitutes for required integrated views, and
incorrect sandbox claims are material completion gaps.
