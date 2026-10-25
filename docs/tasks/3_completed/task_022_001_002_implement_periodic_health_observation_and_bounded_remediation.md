---
id: task_022_001_002
title: Implement periodic health observation and bounded remediation
tier: task
status: completed
parent: feat_022_001
children: []
depends_on:
- task_022_001_001
owners:
- swe
skills: []
parent_rev: d27fd359c1991f129ef13fd64c0d3282de81d8c0
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Implement periodic health observation and bounded remediation

## Parent Feature

[feat_022_001](../../features/2_active/feat_022_001.md)

## Depends on

- task_022_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Integrate direct-report health inspection into the existing supervisor lifecycle using the discovery contract. Read cadence from the established runtime configuration pattern. Classify reports as no-action, remediation-eligible, or unresolved with canonical statuses and legal transitions; exclude terminal reports and terminal supervisors. Perform at most one role-authorized recovery attempt for each unchanged child incident, keyed by child identity plus observed persisted state/version, and handle transient inspection or recovery failures without unbounded retry or duplicate concurrent action. Keep the change narrowly scoped; add no scheduler, taxonomy, dashboard, or notification system.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
