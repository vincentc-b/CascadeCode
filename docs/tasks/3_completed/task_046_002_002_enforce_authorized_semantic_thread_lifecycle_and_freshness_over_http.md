---
id: task_046_002_002
title: Enforce authorized semantic thread lifecycle and freshness over HTTP
tier: task
status: completed
parent: feat_046_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 78a5ad9f24d9e8368e324534b9404c56c6c5ff9a
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Enforce authorized semantic thread lifecycle and freshness over HTTP

## Parent Feature

[feat_046_002](../../features/2_active/feat_046_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add one server-side review-context check for requirement/view/element/relationship thread reads and writes using the active immutable review tuple, owner, repository, pinned target inventory and baseline. Resolve requirement provenance from its pinned document repository; reject forged or stale anchors with a clear conflict response. Reuse the existing thread store, owner routing and human permissions for create, reply, resolve and supported reopen. Keep original source and diff links readable; mark removed/drifted targets outdated on read and retain blocking status through restart, honoring only explicit reviewed renames. Add focused HTTP authorization, stale-anchor, lifecycle and restart coverage; preserve Markdown comment behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
