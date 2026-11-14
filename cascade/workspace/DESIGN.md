# Workspace and architecture design

Purpose: resolve repository roles, manage integration worktrees, and enforce revision-pinned architecture/C4 review contracts. Interfaces are `ProjectContext`, ownership/artifact references, C4 closure/render/diff/review, integration worktrees, inventory, and receipts. Owns `REQ-WORKSPACE-001` (repository roles/destinations are explicit), `REQ-WORKSPACE-002` (reviewed artifacts are revision-bound), and `DEC-WORKSPACE-001` (unreviewed proposals never become accepted lineage).

Evidence: `cascade/workspace/`, `tests/workspace/`, and `tests/architecture/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: missing receipts, unavailable reviews/source revisions, and unread child records block clean historical closeout.

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
