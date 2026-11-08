---
id: epic_043
title: Make dependency manifests authorable during epic planning
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
created: '2026-11-07'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Make dependency manifests authorable during epic planning

## Intent

Prevent missing-manifest deadlocks by giving the owning Epic planning team a scoped, revision-safe way to record either an explicit no-dependencies declaration or a complete dependency manifest before sign-off, feature minting, or later guarded planning actions. Keep dependency declaration separate from execution authority: agents may describe required software and verification, but every installation or upgrade remains subject to the existing authenticated human approval boundary.

### Success criteria

1. The Epic Manager and Epic Architect can read and append a dependency manifest only for their own active Epic, using the canonical manifest schema and expected-revision protection; arbitrary sidecar or cross-Epic writes remain denied.
2. The same scoped planning surface supports an explicit none-required declaration with a complete target environment identity, so legacy active Epics can satisfy their next guarded planning action without fabricated dependencies or direct Python calls.
3. Manifest authoring grants no installation, upgrade, sudo, license, credential, or execution authority. Existing per-dependency authenticated-human approvals and trusted bounded execution remain mandatory and independently auditable.
4. Brief creation/activation and active-Epic planning expose missing_manifest as an actionable authoring step. The War Room and team prompt identify who may declare the manifest and do not present bootstrap review controls that require a nonexistent manifest.
5. Successful manifest creation refreshes canonical readiness and allows ordinary evidence-bound role sign-off and feature mint/dispatch without restarting or cancelling accepted work. Stale revisions, invalid environments, malformed dependency entries, completed/non-owned Epics, and duplicate submissions fail safely and idempotently.
6. End-to-end tests cover a legacy active Epic declaring none required, an Epic declaring real dependencies, stale concurrent writes, cross-Epic denial, preserved human-only installation approval, War Room guidance, restart, and the sign-off-to-feature-dispatch flow.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Reuse cascade.epic.dependency_manifests and the existing dependency-state lock, planning MCP registry, War Room projection, evidence snapshots, and lifecycle gates. Do not add a parallel manifest store or infer none-required from an empty list. Treat manifest declaration as plan authorship and installation approval as a distinct human authorization. Preserve append-only history, optimistic concurrency, owning-worktree isolation, safe serialization, and existing accepted work. No automatic installation or dependency substitution is in scope.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-07 · Human · Brief approved through merge request review.

## Amendment log

_(none)_

## Implementation audit · 2026-11-08

Status: open; partial implementation in `999f79ef`, `b55abca2`, and `bc615b88`. The prior blanket completion claim is withdrawn. Preserve the active Epic plan and its child work; no acceptance criteria are waived.

- Scoped manifest authoring and the none-required → role sign-off → approval → Feature-dispatch path are implemented.
- The closure audit found an in-scope real-dependency defect: operation authority passed an operation string to an approval boundary requiring an InstallationBinding. `bc615b88` fixes this with `InstallationBinding.from_entry`, preserving exact approval and policy checks. All 11 dependency-operation authority tests now pass.
- Criterion 6 still needs complete acceptance evidence for real-dependency authoring through approved execution, concurrent public writes, both planning roles, target/tracking worktree separation, and guidance/activation/restart behavior. Passing the isolated authority suite does not establish that full lifecycle.
