---
id: epic_034
title: Requirements tracker
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: true
models:
  epic_manager: gpt-5.6-terra
  epic_architect: gpt-5.6-terra
  feature_lead: gpt-5.6-terra
  feature_architect: gpt-5.6-terra
  swe: gpt-5.6-terra
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Requirements tracker

## Intent

Make Cascade code track the requirements (functional and non-functional) and design decisions in a DESIGN.md at each directory level unless the level is trivial. Since this is not currently done for the project, we should dispatch teams to do this for each current directory structure, by "replaying" the epics/features/tasks.

### Success criteria

1. A design skill. Look at home/ubuntu/dev/automatik/skills for inspiration. The skill should encourage very concise language, diagrams where modules benefit them. It should specify the scope of the design doc and carefully ensure that the submodule requirements don't bleed to the upper levels in a way that is repeated.
2. a DESIGN.md template. Since these documents can grow over time, it should likely start with a table of contents. The sections should be outlined (start blank) and be aligned with the table of contents.
3. Each design team (epic/feature/task) will have to kick off a review with the design skill to make sure what they implemented is properly reflected in the spec
4. This project's design documents are created and populated by replaying each epic/feature/task that is completed and not cancelled
5. Before a Task, Feature, or Epic closes, its team invokes a design review that checks the affected directory designs and ancestors against the implemented change. The workflow provides an authorized way to propose and merge required document edits. Closure records either the accepted design update or a reason no update was needed; blocking mismatches prevent closure.
6. Coverage: every eligible directory has a populated DESIGN.md; every excluded directory has an identified parent design.
7. Reconciliation: every completed, non-cancelled work item is accounted for in a replay ledger, including items that changed no durable design. A final pass checks parent–child consistency, cross-directory interfaces, links, table-of-contents headings, and claims against current code.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

- Define “trivial” and the document boundary. A directory gets a DESIGN.md when it owns distinct behavior, state, interfaces, or decisions. Generated files, lifecycle folders such as docs/tasks/3_completed, and simple leaf directories are covered by the nearest meaningful parent.
- Give each requirement one home. A parent records system goals, cross-module constraints, and interfaces between children. A child records the requirements and decisions it owns. Parents link to child designs instead of repeating them.
- Make replay evidence based. Use completed, non-cancelled Epic, Feature, and Task records as leads, then check their claims against current code and tests. Mark unresolved gaps; do not present an old plan or unimplemented decision as current behavior.
- Preserve the existing root document. Reconcile DESIGN.md (DESIGN.md) with the new hierarchy through focused edits. Keep work-item history in the work-item records rather than copying it into design docs.
- Keep documents concise and durable. Record functional and non-functional requirements, key decisions and rationale, interfaces, and important flows. Use small Mermaid diagrams when they clarify module relationships or state changes. Avoid task plans and line-by-line code descriptions.
- Specify concurrent ownership. Give each directory design one editing owner during replay, with a review of shared interfaces and ancestor summaries before merging changes

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-03 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
