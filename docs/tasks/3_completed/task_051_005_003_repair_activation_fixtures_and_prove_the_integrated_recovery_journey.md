---
id: task_051_005_003
title: Repair activation fixtures and prove the integrated recovery journey
tier: task
status: completed
parent: feat_051_005
children: []
depends_on:
- task_051_005_002
owners:
- swe
skills: []
parent_rev: 04edd7165032c8e52d8451b0e88e5fa4cfdc6aea
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Repair activation fixtures and prove the integrated recovery journey

## Parent Feature

[feat_051_005](../../features/2_active/feat_051_005.md)

## Depends on

- task_051_005_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Acceptance criteria

- Repair only relevant fixtures in tests/workspace/test_kickoff.py and tests/test_feature_closeout_flow.py. Use normal activation and configured approval so tests reach their idle/no-provider and dependent-Feature release assertions. Resolve the 16 existing_child_work activation refusals and one missing-agent-configuration approval refusal without bypassing guards.
- Run the bounded focused suites for delivery consumers, cross-Feature queued recovery, late repair, review recovery, kickoff and closeout. Show a real temporary Git journey from upstream red CI through unchanged repeated passes and restart, material change, exact intended-target integration and dependent release. Script external forge/provider transport only where needed and name each scripted seam.
- Preserve original Feature/branch/review identity, exact source and target heads, one review for an open repair, approval/CI gates and existing finite Recovery contract. Assert no repeated dependent Task execution or validation on unchanged upstream evidence and one eligible release after verified integration.
- Record before/after focused test outcomes and any remaining historical failures; do not broaden unrelated fixture cleanup. Reconcile test evidence links in owning Task, Watchdog, Workspace and Feature designs where the final behavior changes, and check affected Code source links and native declarations.

## Likely files

tests/workspace/test_kickoff.py, tests/test_feature_closeout_flow.py and existing late-repair/review-recovery harnesses; only directly necessary production or design corrections discovered by integration.

## Limits

No approval shortcut, CI bypass, dependency installation, live forge action or deployment.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
