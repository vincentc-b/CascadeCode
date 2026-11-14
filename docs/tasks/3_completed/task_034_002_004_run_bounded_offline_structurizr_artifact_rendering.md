---
id: task_034_002_004
title: Run bounded offline Structurizr artifact rendering
tier: task
status: completed
parent: feat_034_002
children: []
depends_on:
- task_034_002_003
owners:
- swe
skills: []
parent_rev: 3e54bf6b83555ae4e7f7ee522a1062c74feaa67d
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Run bounded offline Structurizr artifact rendering

## Parent Feature

[feat_034_002](../../features/2_active/feat_034_002.md)

## Depends on

- task_034_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build a background artifact operation using the manifest-pinned Structurizr image by immutable digest for DSL validation, semantic JSON and static export from the confined source closure. Retain the static export and embedded workspace JSON from one render as inputs to task 005's controlled live-cell adapter; stock SVG alone is noninteractive because it strips model IDs. Expose an artifact handoff for task 005 to serialize bound SVG from that same render, without interpreting labels, coordinates, or exporter IDs across separate exports. Enforce --pull=never, no network, resource/time limits, read-only container, non-root user, isolated output paths, and structured errors/cancellation; never install or upgrade dependencies. Cache by source-closure digest, image digest, and render settings, with atomic validated artifacts and source/revision provenance. Expose explicit first, empty, and render-error states for consumers. Exercise the real pinned tool with focused integration coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
