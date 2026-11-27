---
id: task_037_001_001
title: Define effective-selection and diagnostic API contracts
tier: task
status: completed
parent: feat_037_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 272318a21e2b769ed35a2db841f6b233bee7bbff
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Define effective-selection and diagnostic API contracts

## Parent Feature

feat_037_001

## Depends on

None.

## Acceptance criteria

- Add a small, importable code contract under `cascade/agent/` for the shared selection, selection-issue, capability-evidence, role-scope, and reason/remedy vocabulary described below. Downstream Tasks 002–004 must be able to import it without running discovery or a model turn.
- Keep this Task to declarations and safe, pure helpers only. Do not implement selection resolution, provider probing, inventory freshness, evaluator behavior, persistence, or consumer migration; those belong to Tasks 002–005.
- Include one focused contract test that checks deterministic role order and JSON-safe, credential-free projection of representative declarations. Avoid duplicating the full evaluator matrix.
- Commit an authorized source/test change. `docs/features` is owned by the Feature team and is denied to the Task team. The approved prose contract and decisions are already saved there; this Task must not attempt to read, write, or commit that path.

## Files likely touched

`cascade/agent/capability_contract.py` (new), one focused test under `tests/agent/`. Use another source path only if it fits the existing package structure better.

## Implementation notes

This body is self-contained because the Task sandbox denies reads under `docs/features`.

Required scope order: Epic = `epic_manager`, `epic_architect`, `feature_lead`, `feature_architect`, `swe`; Feature = `feature_lead`, `feature_architect`, `swe`; Task = `swe`.

Shared `EffectiveSelection` fields: work ID, tier, role, provider, model ID, nullable explicit reasoning override, nullable effective provider-default reasoning, reviewed Flex bool, effective Flex bool, per-field source/provenance, owning document path and revision, selection fingerprint. The source vocabulary retains `document-role`, `document`, `project-role`, `project-tier`, `project-default`, and `provider-default`; a source identifies its document/config revision. Runtime Flex waiver affects only effective Flex.

Shared `SelectionIssue` fields: work ID, tier, role, stable safe reason code/message, nullable provider/model/reasoning/Flex hints and available source/revision. It must not carry parser exceptions. Shared `CapabilityEvidence` shape distinguishes provider availability, discovery failure kind, verified model catalog with per-model reasoning/Flex, provider Flex, CLI/SDK compatibility, required tool-host compatibility, and unknown evidence. Environmental normalization is for Task 003.

Fingerprint identity is SHA-256 of sorted-key UTF-8 JSON with `schema: selection-v1`, work ID, tier, ordered role scope, each selected role's provider/model/explicit reasoning/reviewed Flex and field sources with revisions, and owning document path/revision. Issues contribute their stable code and available source revisions. Inventory, timestamps, diagnostic text, and runtime waiver are excluded. Task 002 implements hashing.

Reason/classification/remedy declarations:
- `missing_configuration`, `malformed_configuration`, `invalid_model`, `invalid_tier`: deterministic; `migrate_or_default`, `choose_configuration`.
- `unsupported_adapter`: deterministic; `choose_configuration`.
- `provider_not_installed`, `provider_not_authenticated`: transient; `open_provider_setup`, `refresh_and_retry`.
- `discovery_unavailable`, `discovery_empty`, `provider_unavailable`, `provider_temporarily_unavailable`, `capability_unknown`: transient; `refresh_and_retry`, plus `open_provider_setup` when setup evidence exists.
- `model_not_offered`, `reasoning_not_supported`, `flex_mode_not_supported`: deterministic; `choose_configuration`.
- `cli_incompatible`, `sdk_incompatible`, `tool_host_incompatible`: deterministic; `open_provider_setup`.
- `stale_selection`: deterministic; `refresh_and_retry` after selection reconciliation.
- `available`: supported; no remedy.
`continue_without_flex` is a batch-only candidate after fresh whole-batch evaluation with Flex off succeeds; do not grant it from a role declaration.

Keep the existing preflight `supported|unsupported|unavailable` role outcomes and `supported|blocked|transient` batch outcomes. The Task 004 evaluator owns result behavior and additive serialization.

## Skills

_(none)_

## Test plan

Run the focused contract test. The downstream tasks test resolution, normalization, evaluation and consumer parity.

## Out of scope

Feature-spec edits; lifecycle gates; provider turns; credential handling; full consumer migration.
