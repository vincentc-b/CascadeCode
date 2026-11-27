---
id: task_048_003_003
title: Document controlled runtime exercise preflight and verify architecture closure
tier: task
status: completed
parent: feat_048_003
children: []
depends_on:
- task_048_003_002
owners:
- swe
skills: []
parent_rev: a4a20bd3e791e251f3882a60b1314bcbd58cb5b6
created: '2026-11-24'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Document controlled runtime exercise preflight and verify architecture closure

## Parent Feature

feat_048_003

## Depends on

- task_048_003_002

## Acceptance criteria

- Prepare a concrete, read-only preflight for a later controlled operational exercise. Identify the exact product and tracking repository roots and checkout/branch identities, runtime environment and installation destination, reviewed source and integrated target commits, artifact digest plus binding receipt, executing import root, observed worker PID/host boot/process start and capability fingerprint, authorized actor and credential scope, and supported drain/install/restart/postcheck entry points. Name the owned injection point for a broken recovery adapter and for a crash after remote push before local receipt, the authoritative remote-effect comparison, the expected original incident and budget receipt, and a bounded rollback to the prior known-good installation with queued delivery and receipts preserved. For every absent target, artifact, authority, credential or rollback prerequisite, record the exact missing item, owner and next supported action; do not claim the exercise ran or fabricate runtime evidence. Keep the preflight read-only and distinguish proposed injection from an executed fault.
- Reconcile README operator instructions with the implemented bootstrap and loaded-revision contract. Verify approval, installation, credential, clean-checkout, source/target, capability and postcheck gates remain explicit. No software installation, live deployment, operator trunk edit or site-packages hotpatch is authorized.
- Review the final diff against cascade/workspace/DESIGN.md and affected package, Feature, Task, Watchdog and War Room designs. Ensure current matter-of-fact requirements/decisions have one owner, links resolve, execution and failure/restart flows match code, durable state and process boundaries are explicit, and no delivery history or unimplemented behavior is asserted. Record designs reviewed, updates/no-change reasons, checks and gaps in the feature closeout evidence.

## Diagram-impact acceptance

| Level / view | Required reconciliation |
|---|---|
| `cascade-landscape`, `cascade-context`, `cascade-containers` | Verify actual actor, external authority and worker/artifact/storage boundaries against the final diff; record each view key and a source-backed update or no-change result. |
| `cascade-supervisor-components`, `cascade-cli-components`, `cascade-team-components`, `cascade-war-room-components` | Confirm the final responsibility and interface links for launcher, worker, Watchdog, Feature, Task, shared review publication, Workspace, and War Room health consumers. |
| `cascade-workspace-commands-code`, `cascade-workspace-code`, `cascade-watchdog-code`, `cascade-feature-code`, `cascade-task-code`, `cascade-teams-code`, `cascade-dashboard-code`, `cascade-war-room-http-code` | Verify every changed significant symbol has a native custom Code node with correct `cascade.codeComponent`, `cascade.parent`, `cascade.sourcePath`, `cascade.sourceSymbol` and declaration kind; no stale nodes or accepted snapshot rewrite. |
| Owning-design behavior | Trace one normal and one failure/restart scenario against source. Validate model.dsl, views.dsl and workspace.contract.json, local render, Context → Containers → Components → Code, Level up, deep-link restoration and representative pinned source. Report measured cache reuse and limits, not a universal latency claim. |

## Files likely touched

README.md, affected cascade/{workspace,watchdog,feature,task,war_room}/DESIGN.md and cascade/DESIGN.md, architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json} only where the final diff requires correction, and a concise preflight/evidence artifact in the feature work record with target, artifact, authority, injection, rollback and evidence references.

## Implementation notes

This task verifies and closes documentation against the implemented diff. Keep operational target facts and any missing external authority in the work record; designs describe current behavior without feature/task attribution.

## Skills

- skills/design/SKILL.md

## Test plan

Run architecture source-contract validation and supported local render, representative browser navigation with a real view, link checks and focused checks for any documentation/interface corrections. Record exact commands, results and limitations.

## Out of scope

Executing the later operational exercise, installing dependencies, approving installation, live deployment and new product acceptance policy.
