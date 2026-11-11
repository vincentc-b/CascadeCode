---
id: task_034_002_001
title: Prove Structurizr renderer-node metadata join
tier: task
status: completed
parent: feat_034_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 7fd996f728f75e701a8e719928652f2217362651
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove Structurizr renderer-node metadata join

## Parent Feature

[feat_034_002](../../features/2_active/feat_034_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the manifest-pinned Structurizr image and representative DSL fixtures to prove a trusted renderer-node -> exported JSON model ID join for elements and relationships from the same export. Show how the mapping survives reorder, duplicate labels in different containers, and parallel relationships; show removed targets produce no stale hit. Record exact supported metadata and failure behavior. This is the first acceptance gate: if stock SVG/exports cannot provide an unambiguous join, report the blocker and a concrete supported approach before interactive review work proceeds. Tests use the real pinned tool with no network/pull.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
