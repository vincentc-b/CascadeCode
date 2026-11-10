# task_034_002_001 — Structurizr renderer-node join proof

## Result

The acceptance checkpoint passes for a controlled adapter, but **stock SVG by
itself remains unsupported for interaction**. The manifest-pinned
`structurizr/structurizr:2026.09.19-playwright` image at digest
`sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`
was exercised with `--pull=never`, `--network=none`, a read-only root,
dropped capabilities, bounded CPU/memory/PIDs, and temporary outputs.

The pinned static renderer maintains the exact exported model ID on each live
JointJS element and relationship cell. Its public highlight APIs return that
ID for the renderer cell under the pointer. The proof captures the following
tuple before serialization:

`(renderer DOM id, element|relationship, exported model id)`

It then adds only `data-cascade-model-kind` and `data-cascade-export-id` to the
corresponding cell and serializes that same live diagram. The renderer's
embedded `workspace.js` JSON is the semantic model for the same static export;
there is no join across separate exports.

The integration proof applies the binding-specific sanitizer contract after
serialization: event attributes and unapproved `data-cascade-*` attributes are
removed, while exactly `data-cascade-model-kind` and
`data-cascade-export-id` remain. Production sanitization may be stricter for
other SVG content, but it must explicitly allow these two attributes and must
repeat the manifest-to-SVG equality check after sanitization.

## Supported metadata and join

The adapter supports these pinned-renderer cases:

- ordinary rendered elements: renderer model ID directly identifies the JSON
  model element;
- deployment container instances: follow the JSON `containerId` once to the
  owning container (software-system instances are not claimed by this proof);
- rendered derived relationships: follow `linkedRelationshipId` until the
  explicit source relationship is reached; and
- explicit elements and source relationships: read their nonempty
  `properties["cascade.id"]`.

Exporter IDs and renderer DOM IDs are artifact-local. They are retained only
inside one artifact's binding manifest/SVG; `cascade.id` is the durable
identity. Labels, coordinates, source order, SVG order, and transient IDs are
never matching inputs.

The fixture contains two `Region` deployment nodes under different parents,
two `Worker` containers from different systems, and two parallel relationships
with identical endpoints. A reordered fixture changes exporter IDs while
producing the same eight semantic bindings. A removal fixture produces only
the three surviving bindings; the removed container, parent nodes, and both
relationships have no stale result.

## Stock SVG limitation and failure behavior

The pinned `structurizr-diagram.js` deliberately removes `model-id`,
`data-type`, and CSS classes during SVG export. The resulting stock SVG has
only generated IDs such as `j_13` and `v-42`; it contains neither exported
model IDs nor `cascade.id`. Consequently, stock SVG plus separately exported
JSON cannot be accepted as an interactive artifact.

The attribute name deliberately avoids the suffix `model-id`: this pinned
renderer removes that substring with a broad regular expression and would
corrupt `data-cascade-model-id` during serialization.

Artifact creation must fail closed if any rendered hit target lacks a model
ID, a model ID is absent from the embedded JSON, a container/linked-
relationship chain is broken or cyclic, `cascade.id` is empty or duplicated,
two renderer nodes claim one semantic target unexpectedly, or the serialized
SVG attributes differ from the captured manifest. Failure blocks interactive
review and leaves source diff as the supported review surface; it must not
fall back to text, geometry, order, or IDs from another export.

The concrete supported path is therefore: load one pinned static export,
capture renderer cell/model bindings through the renderer's highlight API,
resolve those IDs only against that export's embedded JSON, serialize the live
diagram with the two approved attributes, sanitize, and verify the sanitized
SVG against the separately stored binding manifest. Any failed check produces
an unsupported-mapping artifact state; the review surface links back to the
versioned DSL/source diff instead of enabling diagram hit targets.

The real-tool integration test is
`tests/architecture/test_structurizr_renderer_node_join.py`.
