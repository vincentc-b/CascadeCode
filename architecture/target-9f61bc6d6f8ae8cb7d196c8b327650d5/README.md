# Cascade C4 source contract

`workspace.dsl` is the versioned Structurizr entry point. Its complete local
include closure and ownership are declared in `workspace.contract.json` and
validated with `validate_c4_workspace()` before rendering.

Every reviewable element and explicit relationship has a workspace-unique
`cascade.semanticId` property and a matching contract row. Every view has an
explicit unique key. Numeric IDs, SVG node IDs, coordinates, labels, and source
order are export-local data and never provide semantic identity. Renames retain
continuity only through a nonempty, reviewed `renames` row.

Only confined local `.dsl` includes are accepted. Remote references, plugins,
scripts, workspace extension, unassigned or derived relationships, and dynamic
views fail validation. Dynamic views can be enabled only after their occurrences
have deterministic source/view/occurrence identities in this contract.

## Derived render artifact contract

The renderer accepts a `C4SourceClosure` only when its repository keys, role,
architecture root, revision, owners, repository paths, and per-file SHA-256
values recompute to the recorded closure digest. Immediately before cache
lookup it rejects changed, missing, extra, symlink, or special input files and
copies the verified bytes to a private snapshot. Every Structurizr stage mounts
that snapshot read-only, so later changes to the materialized directory cannot
change a render already in progress.

The immutable cache key covers artifact schema version 4, closure digest, the
pinned Structurizr image digest, and bounded render settings. `manifest.json`
records those values plus the source entry point, full source-file provenance,
view inventory, source-diff reference, binding and SVG paths, and an
`artifact_sha256` map for every regular file under `output/`. Cache reuse
requires an exact source-provenance match, exact output inventory and hashes,
valid semantic/static JSON, matching view inventories, a complete hit-target
manifest, and sanitized SVG attributes. Missing, extra, changed, symlinked, or
unparseable output is `invalid_artifact`; it is never a cache hit.

Successful artifacts have `ready` or `empty` status. A ready artifact provides
the semantic workspace JSON and its verified SHA-256, embedded workspace JSON,
static export, sanitized bound SVGs, hit-target manifest, view keys, and source
diff reference. `binding_error` is explicitly noninteractive and retains the
source diff. Other structured failures distinguish unavailable pinned images,
validation, export, timeout, cancellation, invalid source/cache artifacts, and
internal errors. No failed operation publishes a partial success.

Semantic diff consumes only a ready workspace whose bytes still match the
verified render digest. It resolves model-scoped view fields
(`softwareSystemId`, `containerId`, and `elementId`) through exporter IDs to
semantic identities and rejects broken references; Structurizr's
`deploymentEnvironmentId` is a nonempty environment name. Layout, coordinates,
source order, and exporter IDs are excluded from semantic comparison. Labels
are excluded from identity matching; changed names and descriptions are
compared as semantic properties.

Published reviews persist pinned render, binding, source-diff, and semantic-diff
references as evidence. Failed bindings remain noninteractive. The plan page
renders one derived comparison graph from the union of authorized current and
proposed projections, keeping removed targets and old connections visible.
Interaction attaches only to verified targets; pending/failed rendering is
explicit. The branch Architecture tab continues to display a single pinned
revision. Neither consumer mutates accepted artifacts, matches identity by labels
or geometry, or treats an unverified cache directory as model authority.

The comparison graph is a presentation artifact with its own bounded source
closure, native render, cache identity and verified target mapping. It does not
replace either revision's authored model. The rendering and identity contract is
owned by [Workspace](../../cascade/workspace/DESIGN.md#derived-comparison-rendering);
colors, inspection, navigation and viewport preservation are owned by
[War Room](../../cascade/war_room/DESIGN.md#single-diagram-architecture-differences).

## Historical evidence

`historical-evidence-inventory.json` is the immutable Task 001 pin.
`replay-ledger.json` preserves all 2,023 G row IDs and accounts once for each of
the 16 accepted integration/delta revisions. Every row carries row-specific
rationale, exact current-code/test references, affected architecture IDs, and
explicit unresolved materiality. Canonical work, commit, and review keys remain
many-to-many references rather than duplicated evidence.
`reconciliation-report.json` preserves the original G pin and the separately
accepted Epic pair, records the balanced coverage, and reuses the existing
owner-scoped staged design/C4 review units. The accepted deltas require no new
semantic proposal. Task 003 does not claim final reconstruction closeout while
exact-revision owner review or any material gap is pending.

`final-validation-report.json` is the Task 003 `AcceptanceSummary`. It refreshes
the colocated accepted Epic pair, accounts for every later accepted delta,
rechecks F/G reachability, binds each input artifact by revision and digest, and
records the real pinned Structurizr validation/export/render outputs under
`final-validation/`. It also preserves exact staged review-unit IDs, failed
receipt-validator outcomes, and historical missing receipts. A successful
render is evidence about the authored model bytes; it does not clear pending
owner review, missing receipts, or material provenance gaps.

## Reading the implementation

Start with `cascade-landscape`, `cascade-context`, and `cascade-containers`.
The supervisor overview is `cascade-supervisor-components`; choose
`cascade-team-components` in the Architecture view selector for the team breakdown.
[Package navigation and team execution](../../cascade/DESIGN.md#architecture-navigation)
link the code-level structure, lifecycle, persistence, and recovery diagrams.
[Epic](../../cascade/epic/DESIGN.md), [Feature](../../cascade/feature/DESIGN.md),
and [Task](../../cascade/task/DESIGN.md) contain source-linked implementation views.
The owning designs' Mermaid diagrams complement the integrated Code views;
they are not dynamic Structurizr views or separately deployed services.

The default entry is `cascade-context` (L1), followed by `cascade-containers`
(L2), component views (L3) and authored Code views (L4). Level up stops at context.
`cascade-landscape` is a supporting overview available in the view selector and
through explicit links, not another zoom level. Its current scope matches the
context because the model contains one system and its immediate surroundings;
retain the authored scope for broader multi-system models.

For diagram review implementation, open `cascade-war-room-components`, then
**Diagram comparison** → `cascade-diagram-review-code`. It connects the browser
coordinator, semantic navigation and SVG viewer to the project-preview endpoint.
From the supervisor's **Workspace** component, choose
`cascade-comparison-render-code` to inspect combined graph construction, source
closure materialization and the durable render scheduler. Their owning designs
are [War Room](../../cascade/war_room/DESIGN.md) and
[Workspace](../../cascade/workspace/DESIGN.md).


## Integrated code level

From the supervisor component diagram, Explore **Epic team**, **Feature team**,
**Task team**, or **Tier teams** to open the corresponding `cascade-*-code` view.
These are native Structurizr custom views and custom elements, rendered and
bound by the same offline pipeline as the other levels. The UI names their
level **Code**; they do not represent additional deployed containers.

Each code view declares `cascade.codeComponent` with the owning component's
semantic ID. Code elements declare `cascade.parent` with the same component ID,
plus a confined repository-relative `cascade.sourcePath` and a concrete
`cascade.sourceSymbol`. Select a code element to open the source from the
snapshot's pinned code revision. Level up reverses the verified component link.
Unscoped custom views are not automatically treated as code views.

The source contract validates component scope and path confinement. The render
proves semantic hit targets for custom elements exactly as for C4 elements.
Source content is served through opaque snapshot-authorized resource IDs, never
an arbitrary path parameter, and is displayed as plain text.

Interactive rendering performs validation, JSON/static export, and a single
trusted batch capture of all bound SVGs. One Docker/Java/browser session captures
all views; the redundant stock SVG export is omitted. Artifact schema version 4
invalidates earlier cache entries. Per-file hashes, semantic bindings, bounded
execution, cancellation, and fail-closed publication remain in force.

Completed scheduler operations retain their renderer identity inputs. Reads verify
those pinned inputs and published source provenance rather than recomputing with
today's adapter bytes. The known schema-3 adapter remains readable through an
explicit legacy identity check; its provenance manifest is mandatory. A pending
operation admitted for another renderer fails with a refresh instruction instead
of publishing new adapter output under its old identity.
