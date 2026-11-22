# Workspace and architecture design

Purpose: resolve repository roles, manage integration worktrees, and enforce revision-pinned architecture/C4 review contracts. Interfaces are `ProjectContext`, ownership/artifact references, C4 closure/render/diff/review, integration worktrees, inventory, and receipts. Owns `REQ-WORKSPACE-001` (repository roles/destinations are explicit), `REQ-WORKSPACE-002` (reviewed artifacts are revision-bound), and `DEC-WORKSPACE-001` (unreviewed proposals never become accepted lineage).

Evidence: `cascade/workspace/`, `tests/workspace/`, and `tests/architecture/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: missing receipts, unavailable reviews/source revisions, and unread child records block clean historical closeout.

## Repository initialization and guidance

`REQ-WORKSPACE-INIT-001`: Initialization in a Git repository creates board columns,
default configuration, runtime ignore entries, and missing role/design playbooks
and the design template under `skills/`. Existing configuration and guidance
remain unchanged, including repository customizations. Repeating initialization
restores missing guidance files. No project design is invented from placeholders.

`DEC-WORKSPACE-INIT-001`: The repository's `skills/` tree is packaged as
`cascade._skill_templates`, giving installed distributions and source checkouts
the same authoring guidance without a separately maintained copy. Exclusive file
creation preserves existing files. Agents read the installed repository copies,
so guidance changes follow normal repository review and version control.

Implementation: [initialization](init.py) and [package mapping](../../setup.py).
Verification: [initialization tests](../../tests/workspace/test_init.py) exercise
fresh role-context loading, customization preservation and missing-file repair.
Documentation ownership and semantic review requirements belong to the
[design skill](../../skills/design/SKILL.md).

## C4 code model and rendering contract

- `REQ-WORKSPACE-C4-001`: A code view is a native Structurizr custom view whose
  `cascade.codeComponent` names an existing component semantic ID. Custom code
  elements declare `cascade.parent`, a confined repository-relative
  `cascade.sourcePath`, and a qualified `cascade.sourceSymbol`. Stable IDs and
  the versioned source contract bind model elements, relationships and views.
  Source paths and scope metadata are validated before use; numeric renderer IDs
  never substitute for semantic identity.
- `REQ-WORKSPACE-C4-002`: Rendering validates the pinned source closure, exports
  semantic/static artifacts, and captures all SVGs and semantic bindings in one
  bounded browser session. Sanitization, exact hit-target bindings, artifact
  hashes and provenance remain mandatory. A failed render cannot publish partial
  success. The default total render deadline remains 180 seconds; batching does
  not relax resource or cancellation bounds.
- `REQ-WORKSPACE-C4-003`: Completed snapshots remain readable across renderer
  upgrades using their original persisted identity inputs and source provenance.
  The supported legacy schema-3 identity is explicitly recognized and requires
  its original manifest. Tampered identity/provenance fails. A pending operation
  whose renderer identity changed fails with refresh guidance instead of
  publishing new renderer output under an old identity.
- `REQ-WORKSPACE-C4-004`: Resolving an already-selected checkout inspects only
  that checkout's Git state, while retaining registered identity and branch
  checks. Full catalog discovery can inspect all registered checkouts. Cached
  SVG validation is reused only for identical bytes, view key and bindings;
  files are reread so changed or missing content is detected.

`DEC-WORKSPACE-C4-001`: Code diagrams use Structurizr custom elements/views rather
than inventing deployable containers for functions and types. The HTTP projection
maps validated code views to the fourth-level navigation contract. Supplementary
sequence diagrams in owning designs explain behavior without replacing the code
view.

`DEC-WORKSPACE-C4-002`: One trusted binding adapter produces both SVG and binding
metadata for every view, avoiding per-view Java/browser startup and a redundant
stock SVG export. Artifact schema 4 distinguishes this pipeline. New admissions
use current renderer identity inputs; completed reads use pinned inputs, allowing
upgrades without silently changing historical evidence.

Implementation: [source contract](c4_source.py), [renderer](c4_render.py),
[trusted adapter](RendererBindingAdapter.java), [binding validation](c4_bindings.py),
[scheduler](c4_scheduler.py), [semantic projection](c4_review.py), and
[checkout resolution](architecture_browsing.py).

Verification: [source validation](../../tests/workspace/test_c4_source.py),
[real renderer and cache](../../tests/workspace/test_c4_render.py),
[bindings](../../tests/workspace/test_c4_bindings.py),
[semantic code metadata](../../tests/workspace/test_c4_review.py),
[upgrade/tamper handling](../../tests/workspace/test_c4_scheduler.py), and
[selected-checkout isolation](../../tests/workspace/test_architecture_browsing.py).


## Server-resolved preview snapshots

`REQ-WORKSPACE-C4-005`: A trusted server-resolved architecture selection can pin
code, mapping and documentation revisions independently of the checkout's later
HEAD. Creating that snapshot preserves the same descriptor identity, source
validation, rendering bounds and persisted failure behavior as normal context
selection; it does not change the checkout or accepted review lineage.

`DEC-WORKSPACE-C4-003`: `ArchitectureSnapshotStore.create` resolves a context and
then delegates to `create_selection`. The latter is an internal authority boundary,
not an API for arbitrary client revisions. HTTP callers must authorize selections
before invoking it. The War Room uses this entry point for immutable project
projection commits and binds preview pairs to server-generated association
evidence; preview policy is owned by the
[War Room comparison design](../war_room/DESIGN.md#committed-planning-comparisons-and-project-previews).

Verification: [snapshot tests](../../tests/workspace/test_architecture_snapshots.py)
cover a server-selected base remaining pinned after HEAD advances, distinct
snapshot identities and an unchanged checkout HEAD. Existing snapshot and scheduler
validation applies to these selections as well.


## Derived comparison rendering

`REQ-WORKSPACE-C4-006`: A comparison graph is derived only from the authorized,
pinned current/proposed semantic projections. It retains removed elements and
relationships, merges reviewed renames, and renders both old and new connections
when relationship endpoints change. Distinct displayed graphs have independent
derived identity mappings so changes in another scope cannot overwrite their
labels or connections. Views with identical
semantic identities, labels, types, descriptions and connection endpoints reuse
one layout, preventing arbitrary dependency reordering between levels. Their
navigation, diff states and before/after metadata remain specific to each view.
Missing endpoint evidence and ambiguous derived identities fail explicitly.

`DEC-WORKSPACE-C4-004`: [c4_comparison.py](c4_comparison.py) materializes a temporary
Structurizr custom-view source closure and submits it to the existing durable
[C4RenderScheduler](c4_scheduler.py). This projection flattens conflicting
containment into labeled graph elements; original parent and source metadata stay
in the comparison details. It does not modify authored C4 source, accepted
snapshots, publications, or Git refs. The source digest includes both snapshot
identities; scheduler persistence, cache validation, resource limits and native
SVG binding checks remain in force. Derived bound IDs map back to the original
per-view targets only after validated artifact loading. Internal label
suffixes satisfy Structurizr's global name/relationship uniqueness constraints;
only those generated suffixes are removed from the bound SVG before delivery,
retaining the original rendered labels. Color and interaction are applied by the
shared viewer.

`REQ-WORKSPACE-C4-007`: Combined rendering is bounded to 100 views, 5,000 target
occurrences and 2 MiB of generated source. A response permits at most 4 MiB per
SVG and 16 MiB of combined SVG text. Exceeding a bound is an explicit error, never
a truncated comparison. Pending or failed renders never become a ready graph.
Polling reuses the same render identity and pinned inputs.

Verification: [comparison tests](../../tests/workspace/test_c4_comparison.py)
cover semantic union, reviewed renames, endpoint rewiring, native rendering,
verified SVG delivery and scheduler/cache reuse. The authored
`cascade-comparison-render-code` view links the graph builder, source closure and
scheduler to their actual source functions.
