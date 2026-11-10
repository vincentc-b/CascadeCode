# Design: <project or directory>

<!-- Keep this table of contents aligned with the H2 headings below. -->

## Table of Contents

- [Purpose](#purpose)
- [Requirements](#requirements)
- [Decisions and Rationale](#decisions-and-rationale)
- [Interfaces](#interfaces)
- [Key Flows](#key-flows)
- [Architecture Links](#architecture-links)
- [Verification Evidence](#verification-evidence)
- [Child Designs and Directory Coverage](#child-designs-and-directory-coverage)

## Purpose

State what this directory owns, why the boundary exists, and the parent design it serves. Omit work history and implementation plans.

## Requirements

### Functional Requirements

- `REQ-<SCOPE>-001` — State one observable behavior owned here.

### Non-Functional Requirements

- `REQ-<SCOPE>-002` — State one measurable constraint and its measurement context.

## Decisions and Rationale

- `DEC-<SCOPE>-001` — **Decision:** State the durable choice. **Rationale:** State the constraint or tradeoff that selected it. **Alternatives:** Name rejected options when they matter.

## Interfaces

Describe public and cross-directory inputs, outputs, formats, errors, compatibility promises, and the designs owning the other side. Link to requirement or decision IDs instead of repeating their text.

## Key Flows

Describe only flows needed to understand behavior across components. Prefer a small Mermaid sequence, flow, or state diagram when it is clearer than prose.

## Architecture Links

- Source: `<repository-relative path to the authoritative C4/architecture source, or "None">`
- Rendered views: `<repository-relative links, or "None">`
- Scope note: `<what the model covers, or why no separate model is authoritative>`

## Verification Evidence

| Requirement | Evidence | Status or gap |
|---|---|---|
| `REQ-<SCOPE>-001` | `<test path, scenario, review revision, or other inspectable evidence>` | Verified / unresolved with reason |

Record durable evidence, not a step-by-step test plan or a claim based only on an old task or commit message.

## Child Designs and Directory Coverage

| Path | Coverage |
|---|---|
| `<meaningful-child>/DESIGN.md` | Link and summarize the boundary; do not repeat child requirements or decisions. |
| `<trivial-child>/` | Covered here because it has no distinct behavior, state, interface, or decisions. |
| `<generated-child>/` | Generated; covered by this parent and excluded from design ownership. |
