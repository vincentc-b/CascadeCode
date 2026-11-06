---
id: epic_039
title: Dependency validation and feature zero
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
created: '2026-11-06'
updated: '2026-11-06'
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
# Dependency validation and feature zero

## Intent

Make external toolchain, runtime, service, and package prerequisites an explicit bootstrap phase before ordinary feature delivery. During epic planning, the team lists and validates required dependencies in the actual execution environment. Treat this bootstrap as a narrowly authorized "feature 0": agents may install pinned dependencies when policy and permissions allow; otherwise Cascade blocks safely and gives the human exact investigation, installation, and verification steps. After the human installs or resolves the dependency and pings the team, validation reruns and planning resumes without restarting the epic.

### Success criteria

1. Every epic plan records an explicit dependency manifest before ordinary feature minting. Each entry includes name, purpose, selected version/range, authoritative source, install scope, execution environment, license/security considerations, verification command, and evidence or an explicit "none required" result.
2. Cascade runs dependency checks in the same environment that will plan, build, test, or render the work. Host, container, worktree, remote runner, and agent sandbox differences are visible rather than inferred.
3. Bootstrap work is a first-class, board-visible pre-feature phase ("feature 0" semantics) with a narrow human-reviewed scope. It can perform feasibility checks and dependency setup needed to finish the full epic plan without preapproving ordinary implementation features.
4. Agents may install dependencies only when current policy permits the exact mutation. Prefer project-local, user-local, containerized, reversible, version-pinned installs with checksums/digests. Never silently use sudo, change system-wide defaults, add credentials, accept licenses, publish externally, or follow moving `latest` references.
5. If installation is not permitted or feasibility needs human judgment, the epic enters a visible dependency-blocked state. The human receives the failing check, why the dependency is required, exact safe install/investigation steps, expected verification output, cleanup/rollback guidance, and a clear "ping team after completion" action.
6. A human ping resumes the existing planning run, rechecks every blocked dependency, records immutable evidence, and proceeds only when checks pass. Repeated pings and installs are idempotent; accepted work and planning history are preserved.
7. Dependency evidence is revision-bound: selected versions, distribution hashes/image digests, transitive lock data where available, check outputs, and the manifest revision are attached to sign-off. Changes invalidate only affected authorization.
8. Detect circular planning gates. A feasibility adapter or tool needed to validate the main plan must be allowed inside the bootstrap scope, or the plan must surface an explicit human decision; it must not require an unmintable ordinary feature to satisfy pre-mint sign-off.
9. War Room shows dependency status, responsible actor (agent or human), last check, actionable failure, and resume control. Agent chat summarizes live state from the manifest/check result rather than stale prose.
10. Tests cover successful agent-local/container installation, denied system installation, offline/unavailable sources, checksum mismatch, license/credential prompts, human install plus ping/resume, environment mismatch, partial setup recovery, and a no-dependency epic.
11. Apply the workflow to epic_034's Structurizr prerequisite as an acceptance scenario: identify the host Java mismatch, allow a pinned containerized distribution, record its immutable digest and bundled runtime, and keep adapter feasibility distinct from dependency installation.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Build on existing planning sign-offs, lifecycle locks, provider recovery patterns, and War Room action/retry surfaces. Installation authority must be explicit and least-privilege. Do not turn dependency setup into unrestricted shell access. Keep software dependency validation distinct from work-item `depends_on`, while presenting both coherently to humans.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-06 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
