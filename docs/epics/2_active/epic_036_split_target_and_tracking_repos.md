---
id: epic_036
title: Split target and tracking repos
tier: epic
status: active
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-05'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Split target and tracking repos

## Intent

Allow a Cascade project to keep its planning and workflow artifacts in a Git repository separate from the source repository being changed. This prevents epic, feature, and task material from polluting the target codebase while preserving the current colocated model for users who do not opt in.

The target repository remains the place where source worktrees, implementation changes, builds, and tests run. The tracking repository becomes the source of truth for versioned Cascade planning artifacts.

## Success criteria

- A project can select a tracking repository in Cascade's top-level TOML or YAML configuration.
- When the setting is omitted, Cascade behaves exactly as it does today and stores tracking artifacts with the target repository. Existing projects require no migration or config edit.
- When configured, epic, feature, and task documents and their versioned workflow metadata are read and written only in the tracking repository; normal source and worktree operations remain in the target repository.
- The tracking repository may be an existing local checkout or a Git remote that Cascade can prepare in a managed local location.
- Remote Git operations use the user's existing Git/SSH configuration and credential helpers. Cascade neither asks for nor stores repository credentials.
- Invalid configuration, an unavailable repository, or failed Git authentication produces an actionable error before Cascade claims that a planning mutation succeeded.
- A high-signal end-to-end test demonstrates both modes: the current colocated default and a separately configured tracking repository.
- User-facing configuration and recovery behavior are documented.

## User contract

Cascade operates with two explicit repository roles:

1. **Target repository:** source code, implementation branches/worktrees, builds, and tests.
2. **Tracking repository:** Cascade-owned, versioned epic/feature/task artifacts and the metadata required to manage their lifecycle.

The top-level project config gains one optional tracking-repository reference. The exact key spelling and normalized internal type are owned by the first feature, but TOML and YAML must express the same semantics.

A reference may identify an existing local checkout or a cloneable Git remote. A remote is prepared in a deterministic Cascade-managed location. Relative local paths resolve from the config file's directory, not from the process working directory.

Omitting the reference aliases the tracking role to the target repository. This is the compatibility path and preserves the existing on-disk layout and behavior.

## Non-goals

- Moving source code, implementation branches, or build/test execution into the tracking repository.
- Automatically migrating existing planning history between repositories. Initial adoption may use an operator-documented Git move/copy procedure.
- Building a credential store, SSH key manager, or interactive authentication flow.
- Supporting cross-repository atomic commits or distributed transactions.
- Redesigning the epic/feature/task document format or lifecycle.
- General multi-repository source orchestration beyond the target/tracking split.

## Macro-architecture

Introduce a repository-role boundary near project/config initialization:

- **Configuration and resolver:** Parse the optional tracking reference, normalize it, and resolve both target and tracking repository contexts. When absent, both roles point to the same context.
- **Repository preparation:** Validate an existing local checkout or prepare a remote-backed checkout using the system Git client and existing user authentication. Preparation is idempotent and fails with repository-specific diagnostics.
- **Planning storage boundary:** All epic, feature, task, decision, comment-backed planning mutations, and related reads receive the tracking context rather than discovering a repository from the current working directory.
- **Execution boundary:** Source discovery, feature/task implementation worktrees, code commits, builds, and tests continue to receive the target context.
- **Git persistence:** Tracking commits and synchronization occur only in the tracking repository. Cascade reports a planning mutation as successful only after its required local persistence completes; remote synchronization failures remain explicit and recoverable.

No cross-repository transaction layer is introduced. Operations that involve both roles must order and report their steps so that recovery is deterministic.

## Cross-module constraints

- Preserve all behavior and paths for projects without the new setting.
- Do not infer repository role from the current working directory after project initialization; pass or retrieve the resolved role explicitly.
- Never serialize credentials, private-key material, or credential-helper output into config, logs, documents, or errors.
- Redact credential-bearing URL components in diagnostics.
- Avoid target-repository writes caused solely by planning activity when split mode is enabled.
- Repository preparation and retries must be idempotent; an interrupted clone or sync must not be mistaken for a valid checkout.
- Reject unsupported repository references and non-Git directories early with a clear remediation message.
- Maintain existing authorization and path-safety checks independently for both repository roots.
- Prefer system-level coverage of the two repository modes over mock-heavy tests of Git internals.

## Core dependencies

- Existing top-level project config loading for TOML and YAML.
- Existing repository/worktree abstraction and system Git invocation.
- Epic, feature, task, decision, and planning-document persistence paths.
- Project startup and War Room lifecycle code that establishes repository context.
- Existing end-to-end test harness capable of creating temporary Git repositories.

No new credential, hosted-Git, database, or project-management dependency is required.

## Feature breakdown

### Feature 1 — Resolve the optional tracking repository

Deliver the repository-role model and configuration contract.

Acceptance criteria:

- TOML and YAML accept one equivalent optional tracking-repository reference.
- Omission aliases tracking to target and passes existing compatibility coverage unchanged.
- Local references resolve relative to the config location; remote references resolve to a deterministic managed checkout.
- Existing checkouts and clone preparation are validated idempotently.
- Git uses the existing environment/configuration, with no Cascade-owned credential prompt or storage.
- Invalid paths, unsupported references, clone failures, and authentication failures return actionable, redacted diagnostics.
- The resolved target and tracking contexts are available explicitly to downstream services.

### Feature 2 — Route planning lifecycle through the tracking repository

Adopt the resolved tracking context across the complete planning lifecycle and prove the split behavior.

Depends on: Feature 1.

Acceptance criteria:

- Epic, feature, and task create/read/update/list flows, decision history, and required versioned lifecycle metadata use the tracking repository.
- Source changes and implementation worktrees continue to use only the target repository.
- In split mode, an end-to-end scenario creates and advances planning artifacts in the tracking repository while leaving the target repository free of those artifact changes.
- A colocated end-to-end scenario proves unchanged default behavior.
- Failure tests cover unavailable tracking storage and failed Git synchronization without false success reporting.
- Documentation covers configuration, local versus remote references, required preconfigured Git/SSH access, adoption of existing artifacts, and recovery from interrupted preparation or sync.

## Delivery sequence

1. Feature 1 establishes the contract and resolver without changing default behavior.
2. Feature 2 switches planning consumers to the tracking role and supplies end-to-end proof and operator documentation.
3. The epic is complete only when both colocated and split modes pass their system-level acceptance scenarios.

## Open questions

None at epic scope. Exact config-key naming, managed-checkout location, and synchronization mechanics may be selected in Feature 1 provided they honor this contract.

## Decision log

- 2026-11-05 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
