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

| Level | View and scope |
|---|---|
| L1 System context | `cascade-context` shows the operator, Cascade, Git forge, model provider and local Structurizr tooling. |
| L2 Containers | `cascade-containers` shows the Operator CLI, War Room, Service, repository artifacts and direct external dependencies. The CLI supervises the worker. The HTTP server and watchdog share the worker process. Repository artifacts are the Git-backed data store. |
| L3 Components | `cascade-cli-components`, `cascade-war-room-components` and `cascade-supervisor-components` expand the application boundaries. `cascade-team-components` focuses on the tier graphs and their collaborators. |
| L4 Code | Every modeled Cascade component has a scoped Code view. Use [the component index](../../cascade/DESIGN.md#architecture-navigation) to find each view and its owning design. |

The War Room starts at system context. Select Cascade, then an application
container, then a component to reach its code. **Level up** retraces that
path and stops at context. `cascade-landscape` is available in the view selector.
The owning designs' Mermaid diagrams supplement the structural views with
execution, persistence and recovery flows.

## Integrated code level

Read the kind label under a code box's name. It comes from the second quoted
field of the Structurizr `element` declaration, exported as `metadata`. The
War Room also shows that kind in the selected node's details and in the
comparison's before/after **type** field. [Structurizr element syntax](https://docs.structurizr.com/dsl/language#element)

| Label | How to recognize it in source | Example |
|---|---|---|
| Function | Python `def` or `async def`, or a JavaScript `function` declaration | [`ensure_epic_graph`](../../cascade/epic/graph.py) |
| Method | Function declared on a class, written as `ClassName.method` in the source symbol | [`WarRoomRequestHandler.do_GET`](../../cascade/war_room/server.py) |
| Class | Concrete class declaration | [`C4RenderScheduler`](../../cascade/workspace/c4_scheduler.py) |
| Dataclass | Python class decorated with `@dataclass` | [`BoardIndex`](../../cascade/board/types.py) |
| TypedDict | Python class declaring the keys and value types of a dictionary | [`EpicGraphState`](../../cascade/epic/state.py) |
| Interface | A structural contract declared with Python's `Protocol` | [`HumanIdentityVerifier`](../../cascade/war_room/human_auth.py) |

Each code view declares `cascade.codeComponent` with the owning component's
semantic ID. Code elements declare `cascade.parent` with the same component ID,
plus a confined repository-relative `cascade.sourcePath` and a concrete
`cascade.sourceSymbol`. Use the description for the declaration's responsibility,
framework or return value. Select a box and choose **Open pinned source** in
the Architecture tab to read its file at the snapshot's code revision. Follow
the displayed symbol to find the declaration.

The source contract checks component references and path confinement. The
[renderer integration test](../../tests/workspace/test_c4_render.py)
checks that each component has a Code view, that Code nodes belong to their
view's component, and that every authored kind and symbol matches the source.
The renderer verifies semantic hit targets and the HTTP API serves plain-text
source through snapshot-authorized resource IDs.

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
