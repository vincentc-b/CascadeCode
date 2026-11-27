# Exact merge validation planning architecture review

The committed Feature plan at `9830d168dc54c580417b4caa90c3b81ecb3c3e1c` assigns isolated candidate construction, bounded
validation admission, accepted merge observation, and final architecture
reconciliation to three Tasks in dependency order. This planning revision changes
work records only. Its current architecture impact is `no_diagram_change`; the
Tasks remain responsible for updating designs and integrated views against the
implemented source.

## Reviewed ownership and current behavior

Reviewed `DESIGN.md`, `cascade/DESIGN.md`, `cascade/task/DESIGN.md`,
`cascade/workspace/DESIGN.md`, `cascade/boss/DESIGN.md`, and
`cascade/board/DESIGN.md` against the current review and publication source.
The package design links the normal publication and failure/restart flow to
`cascade-teams-code`. Its validator profile, reservation, board scan, check,
and publication nodes belong to `element.component.teams`. Task owns the
incident budget and operation receipts; Workspace owns checkout lifecycle;
Boss consumes acceptance evidence. The current package design explicitly
limits source checkout checks: they do not prove the exact prospective or
accepted target result. The current model, views, and source contract are under
`architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/`.

The revised plan specifies candidate, validation material, receipt, and accepted
merge identities; the shared matcher; and drift, failure, and restart behavior.
These are Task contracts, not claims about current product behavior. No
`DESIGN.md` or architecture source changed in this planning revision. The
existing C4 context and container boundaries remain accurate for the current
code. The plan assigns Teams code-view changes to the implementation Tasks and
requires final source-linked normal, drift, timeout, and restart review.

## Diagram impact and delivery owner

| Level / view | Planning review and delivery requirement |
|---|---|
| `cascade-context`, `cascade-containers` | No current actor, external system, runtime or persistence boundary changed. Task 3 verifies this against the integrated diff. |
| `cascade-supervisor-components`, `cascade-team-components` | Tasks 1 and 2 reconcile Teams collaboration with Task, Workspace and Boss; Task 3 checks the final relationships. |
| `cascade-teams-code` | Tasks 1 and 2 extend the existing Teams validator and publication owner with real declarations and source metadata. Task 3 checks navigation and stale symbols. |
| `cascade-task-code`, `cascade-workspace-code`, `cascade-boss-code` | Tasks update only changed budget, checkout or consumer symbols; Task 3 records a final diff grounded result for each. |
| Owning-design behavior flows | Tasks trace exact candidate success, red assertion, drift, timeout, restart and accepted merge observation against code. |

## Verification and open obligations

`/opt/conda/bin/python3.12 -m pytest -q tests/workspace/test_c4_source.py`
passed: 14 tests. `git diff --check` passed before saving this artifact.
These checks cover the current C4 source contract and clean planning base.
No implementation result, pinned render, browser navigation or exact merge
validation is claimed. Tasks 2 and 3 carry those gates in their primary acceptance
sections. Task 1's canonical active primary acceptance section still says `TBD`;
its detailed `## Acceptance` section and the Feature-owned delivery contract
contain the requirements. A supported lifecycle reconciliation of the primary
section remains required before Feature completion. The
exact publication request is saved in
`feat_054_001_architecture_review.json`.
`publish_architecture_review` returned `no_diagram_change` for the exact
`9830d168dc54c580417b4caa90c3b81ecb3c3e1c` plan, operation
`architecture-publication-114ba43c5776700dd3aa313d83fed43b4b6088c5c3d3c9cfdbdb54e8dd66e876`
and review unit
`architecture-review-eeda9b77151b827af73e049639ea625d4261f2e7fec0e14bc1adc4ea801a26ad`.
The request used the absent accepted Epic lineage generation (`null`). The
earlier receipt covered only revision `e164a8bd`; implementation and final
integrated architecture reconciliation remain Task obligations.
