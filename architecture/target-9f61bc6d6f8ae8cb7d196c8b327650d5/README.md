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

The immutable cache key covers artifact schema version 3, closure digest, the
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

Feature C may persist these pinned render, binding, source-diff, and semantic
diff references as review evidence, but must not reinterpret failed bindings
as interactive. Feature D may display paired views and attach interaction only
to verified manifest targets; it must preserve the source-diff fallback for
missing, ambiguous, removed, or invalid targets. Neither consumer may mutate or
silently repair these artifacts, match by labels or geometry, or treat an
unverified cache directory as a model authority.
