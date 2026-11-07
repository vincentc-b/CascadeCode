---
id: feat_039_001
title: Dependency manifests, evidence, and planning gates
tier: feature
status: active
parent: epic_039
children:
- task_039_001_001
- task_039_001_002
- task_039_001_003
- task_039_001_004
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: e7070c3c4b1fcaad33b20680284adc1c3792f253
created: '2026-11-06'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
reasoning:
  feature_lead: high
  feature_architect: high
approved_at: '2026-11-07T01:25:11.503797+00:00'
---
# Dependency manifests, evidence, and planning gates

## Parent Epic

epic_039

## Scope

Implement slice A of epic_039. Add durable revisioned dependency manifests (including explicit none required), append-only check attempts tied to actual environment identity, and immutable evidence snapshots bound to planning sign-off. Enforce current readiness at ordinary feature mint, sign-off, and plan approval using existing lifecycle/tracking-repository primitives. Missing, stale, unknown-environment, or unresolved-feasibility evidence blocks. Invalidate only affected dependency authority; preserve existing whole-plan revision sign-off rules. Existing epics require a manifest at their next planning action without restarting or cancelling accepted work. Keep software dependencies distinct from work-item depends_on. Acceptance: integration tests for absent/empty manifests, matching/mismatching environments, stale attempt completion and revisions, selective invalidation, and all guarded entry points. Define schemas and public transition contracts needed by slice B. No installation runner or new work-item tier in this slice.

### Per-dependency installation authority

Every dependency installation or upgrade requires explicit human approval bound to dependency ID, exact version, authoritative source, checksum/digest, target environment, install scope/destination, exact operation, and cleanup plan. Persist an independent approval for each entry with human provenance and the reviewed binding. Epic/feature plan approval and bootstrap review alone grant no installation authority. Provider `yolo` and owned-worktree access provide execution capability only. Cascade must enforce the approval at the operation boundary before mutation, independently of the provider sandbox and in addition to current execution policy.

A batch UI may approve several entries in one interaction only if it persists independent per-entry approvals. Any change to dependency ID, version, source, digest, environment, scope/destination, operation, or cleanup plan invalidates only that entry's approval; unchanged entries retain theirs. Read-only discovery and validation may proceed without installation approval. Checks that install, upgrade, or implicitly pull dependencies must pass the installation gate. Plan sign-offs, resume/ping, and successful checks never create installation approval.

Define canonical approval records and public validity/invalidation contracts for slice B: exact binding, approver identity/time, reviewed entry snapshot/revision, and attempt-to-approval references. Keep installation approvals distinct from plan sign-off, readiness evidence, and feasibility authorization. Whole-manifest revision changes do not revoke approvals whose bound fields are unchanged; verification-recipe changes invalidate affected evidence. Acceptance must cover every binding field, independent approvals from one batch, unchanged-entry survival, and plan approval producing no installation authority. Preserve existing integration tests and the no-installation-runner boundary of this slice.

## Data structures

- Epic-owned, tracking-repository manifest sidecar: schema version, epic ID, monotonic revision, author/time, and either an explicit validated none_required marker or a nonempty list of entries. An absent sidecar is missing, and an empty entry list without none_required is invalid. Software dependency IDs are stable within the epic and never use board depends_on.
- Each entry records ID, name/purpose, requested range and resolved exact version when known, authoritative source, checksum or image digest when available, install scope and destination, exact target environment descriptor, verification recipe and expected result, license/security notes, transitive lock references when available, and explicit unknown values. Declared feasibility requirements identify the needed proof and stay unresolved until independently evidenced. A prospective install or upgrade with unknown exact version, source, or integrity digest cannot be approved.
- Keep separate per-entry fingerprints for installation approval and verification evidence. The installation binding covers ID, exact version, source, digest, target environment, scope/destination, operation, and cleanup plan. The evidence binding covers ID, requested range and resolved version (including explicit unknowns), source and integrity references, target environment, scope/destination, verification recipe and expected result, and declared feasibility proof requirements. A change only to the setup operation or cleanup plan invalidates the affected installation approval without invalidating an otherwise current read-only check. A manifest revision alone changes neither fingerprint.
- Check journal records are append-only: admitted and completed events share an attempt ID and carry dependency ID, manifest/entry/recipe revisions, exact operation, times, actual environment fingerprint (runner, repository/worktree, sandbox, runtime, and container digest when applicable), status, redacted output, selected version and integrity/lock references, and an approval ID for any setup attempt. A completion remains historical when its admission is stale. Immutable evidence snapshots name the current manifest and the accepted attempt IDs and fingerprints used at sign-off; an explicit none_required manifest yields an empty snapshot.
- Installation approvals are independent immutable records with approval ID, human approver identity/time, reviewed entry snapshot/revision, and the complete installation binding. A batch writes one record per entry. Plans, sign-offs, pings, and checks never mint approvals.

## API contracts

- Manifest read, validate, and compare-and-swap write operate in the owning tracking repository under lifecycle serialization. Reject duplicate IDs, missing required fields, ambiguous empty manifests, and stale expected revisions. Reading never synthesizes a manifest for an existing epic. Explicit none_required is a durable, valid state.
- Reconcile the merged schema with a versioned reader before planning gates rely on it. Preserve historical manifest snapshots and monotonic revisions without inferring absent contract fields. A legacy entry needs a new fully specified revision before it can provide current readiness or installation authority. Actual environment identity comes from a trusted check attempt; a manifest-supplied actual environment is never evidence.
- Check admission returns a stable attempt ID after validating the current entry, recipe, and target context. Trusted completion records the actual execution environment from the runner context, not a caller-provided claim. Compare target and actual identities field by field for the declared runner, repository/worktree, sandbox, runtime, and container digest where applicable; an unknown required field never matches, while an explicit not-applicable field is distinct from unknown. A result counts as current evidence only when its evidence fingerprint still matches and its actual environment matches the declared target. Slice A defines this recorder and projection; slice B supplies the bounded runner.
- Approval recording requires an authenticated human actor and the full exact binding. Current-validity lookup compares the stored binding to the current entry, independent of whole-manifest revision. The public operation-boundary guard fails closed for missing/stale approvals, unspecified digests, or mismatched operation, and remains distinct from execution policy. Read-only discovery and validation require no installation approval. Slice A exposes the guard; slice B must call it immediately before every install, upgrade, or implicit pull.
- Dependency readiness returns structured blockers for missing/invalid manifest, missing/stale check, unknown or mismatched environment, and declared but unresolved feasibility. Explicit none_required passes without a setup attempt. Every guarded planning action recomputes readiness; an earlier projection is never authority.
- Sign-off records retain the existing plan-revision binding and additionally reference an immutable dependency-evidence snapshot. Both role sign-offs must refer to current valid evidence at plan approval. If dependency evidence changes while the epic plan revision remains the same, each affected role can append a new sign-off against a fresh immutable evidence snapshot; earlier sign-offs remain historical, and idempotence applies only to the same role, plan revision, and evidence binding. A changed epic document still requires both current-revision role sign-offs. A changed dependency or verification recipe invalidates only affected evidence; changed installation binding invalidates only that entry's approval. Plan approval does not create installation authority.

## Logic flow

~~~mermaid
flowchart TD
  M[Read current epic manifest] --> V{Valid manifest?}
  V -- No --> B[Return dependency blockers]
  V -- None required --> G[Planning action may proceed]
  V -- Entries --> C[Project current accepted checks]
  C --> E{Target and actual environments match?}
  E -- No --> B
  E -- Yes --> F{Evidence and feasibility current?}
  F -- No --> B
  F -- Yes --> G
  G --> S[Bind sign-off to plan revision and evidence snapshot]
  S --> A[Recheck both bindings at approval]
~~~

## Task breakdown

1. task_039_001_001 — manifest schema, revisioned persistence, and environment contracts.
2. task_039_001_002 — append-only attempts, current-evidence projection, and snapshots; depends on 001.
3. task_039_001_003 — independent human installation approvals and boundary guard; depends on 001.
4. task_039_001_004 — guarded mint, sign-off, and approval; depends on 002 and 003.

## Risks & upward questions

None.

## Decision log

- `dec_001` · 2026-11-07 · Feature Lead · **Data structures**
  Chose Use an explicit revisioned epic manifest with per-entry installation and evidence fingerprints; keep attempts, evidence snapshots, and human approvals as separate durable records.
  Rationale: Per-entry fingerprints preserve unaffected authority across whole-manifest edits, while immutable attempt and snapshot records make stale completions and sign-off evidence auditable.
  Honors: epic_039 selective invalidation, actual-environment evidence, independent approval, and existing whole-plan sign-off rules.

- `dec_002` · 2026-11-07 · Feature Lead · **API contracts**
  Chose Slice A exposes an approval guard and trusted check recorder without an installation runner; slice B must invoke the guard at every mutation boundary.
  Rationale: This keeps the first slice shippable and prevents a persisted approval or approved plan from being mistaken for permission to execute setup.
  Honors: feat_039_001 no-installation-runner boundary and epic_039 per-operation human authorization.

- `dec_003` · 2026-11-07 · Feature Architect · **Data structures and API contracts**
  Chose Separate installation-approval and verification-evidence fingerprints by their relevant fields; compare declared and actual environment identity field by field, treating unknown as nonmatching..
  Rationale: Cleanup-plan or setup-operation edits should revoke only the affected installation approval when the verified dependency and check recipe are unchanged. Explicit environment comparison prevents a host or partially identified check from satisfying a sandbox or container target.
  Honors: epic_039 selective invalidation and actual-environment evidence; feat_039_001 independent installation authority and current-readiness contracts..

- `dec_004` · 2026-11-07 · Feature Architect · **API contracts**
  Chose Upgrade the merged v1 manifest schema through versioned reads while preserving historical snapshots; require a fully specified new revision for current readiness, and take actual environment identity only from trusted check attempts..
  Rationale: The merged schema lacks required per-entry fields and ties all entries to one target while storing a caller-supplied actual environment. Legacy records remain auditable, but missing fields cannot be treated as proof or installation authority.
  Honors: feat_039_001 current-readiness, per-dependency environment and approval contracts; epic_039 actual-environment evidence and selective invalidation..

- `dec_005` · 2026-11-07 · Feature Architect · **API contracts**
  Chose Allow a planning role to sign the same epic plan revision again when its dependency evidence changes, appending a sign-off bound to a fresh immutable evidence snapshot while retaining earlier records as history..
  Rationale: Sign-offs keyed only by role and plan revision cannot recover from selective dependency evidence invalidation when the epic document is unchanged. A new snapshot binding lets each role renew its own sign-off without forcing an unrelated plan edit.
  Honors: feat_039_001 current-evidence sign-offs and selective invalidation; epic_039 existing whole-plan revision sign-off rules..

## Closeout

Completed child work: `task_039_001_001` (Persist revisioned dependency manifests and environment contracts), `task_039_001_002` (Record dependency check attempts and immutable readiness evidence), `task_039_001_003` (Persist independent per-dependency installation approvals), `task_039_001_004` (Enforce dependency readiness at planning entry points).
