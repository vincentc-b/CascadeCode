---
id: task_039_001_002
title: Record dependency check attempts and immutable readiness evidence
tier: task
status: completed
parent: feat_039_001
children: []
depends_on:
- task_039_001_001
owners:
- swe
skills: []
parent_rev: 107699ab02abe6cdaadf5b5f75e94834a6ae4662
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Record dependency check attempts and immutable readiness evidence

## Parent Feature

[feat_039_001](../../features/2_active/feat_039_001.md)

## Depends on

- task_039_001_001

## Acceptance criteria

- An admitted check and its completion are durable append-only records with one stable attempt ID, manifest/entry/recipe revisions, dependency ID, exact operation, trusted actual-environment fingerprint, timestamps, result, redacted output, and version/integrity/lock references. Installation/upgrade attempts require an approval reference; a read-only check does not.
- Current-evidence projection accepts only a completed, successful check matching the current entry and verification recipe and a complete actual environment matching the target. Unknown or mismatched environment and stale completion block readiness while preserving history.
- An immutable snapshot can name the accepted attempts and fingerprints for a manifest revision. Changing one entry or recipe invalidates only its evidence; unrelated entries remain current. Changed environment invalidates only checks that require it.
- Focused integration/API tests exercise append-only history, matching and mismatching environments, stale admission/completion, revision changes, selective invalidation, and snapshot immutability.

## Files likely touched

cascade/epic dependency evidence module; cascade/board context and Git persistence helpers as needed; tests/epic dependency evidence integration tests.

## Implementation notes

Build append-only check-attempt records in the owning tracking repository with attempt identity, manifest and recipe revisions, dependency ID, actual environment fingerprint, operation, timestamps, result, redacted output, and version/integrity/lock references. Define immutable evidence snapshots for planning sign-off and a current-evidence projection that rejects mismatched or unknown environments, stale attempt completions, changed verification recipes, and changed entries while retaining historical attempts. Invalidate only affected dependency/feasibility evidence. Expose admission/completion contracts for slice B; do not add a runner. Cover matching/mismatching environments, stale completions and revisions, and selective invalidation with integration tests.

## Skills

_(none)_

## Test plan

Use deterministic trusted-recorder integration tests against a temporary tracking repository. Assert persisted records and current projections after reload; do not mirror pure helper logic in extra unit tests.

## Out of scope

No command execution, installation runner, automatic environment discovery from untrusted request fields, or War Room UI.
