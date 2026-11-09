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
