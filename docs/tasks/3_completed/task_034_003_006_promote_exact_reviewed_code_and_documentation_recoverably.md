---
id: task_034_003_006
title: Promote exact reviewed code and documentation recoverably
tier: task
status: completed
parent: feat_034_003
children: []
depends_on:
- task_034_003_005
owners:
- swe
skills: []
parent_rev: 37a365b227ed51c9ab6f3e7792e5e547dfc6d8e0
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Promote exact reviewed code and documentation recoverably

## Parent Feature

[feat_034_003](../../features/2_active/feat_034_003.md)

## Depends on

- task_034_003_005

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Integrate code and documentation together for one repository where possible. For split repositories, journal before merge, merge approved implementation into its owned lineage first, then exact reviewed documentation into its fixed destination. Only both accepted sides advance the lineage architecture pointer and completion. A partial merge remains acceptance_pending and holds affected downstream work. On retry inspect refs/ancestry, recognize landed sides, and run only the missing operation; conflicts, changed heads, or changed revision pairs require re-review. Preserve accepted child baseline without advancing target trunk.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
