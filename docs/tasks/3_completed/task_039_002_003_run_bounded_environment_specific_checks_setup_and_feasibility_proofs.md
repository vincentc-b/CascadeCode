---
id: task_039_002_003
title: Run bounded environment-specific checks, setup, and feasibility proofs
tier: task
status: completed
parent: feat_039_002
children: []
depends_on:
- task_039_002_001
- task_039_002_002
owners:
- swe
skills: []
parent_rev: fd536bb5f3dd24e1337c81f93e397d6e3f2c3a09
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Run bounded environment-specific checks, setup, and feasibility proofs

## Parent Feature

[feat_039_002](../../features/2_active/feat_039_002.md)

## Depends on

- task_039_002_001
- task_039_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the bounded runner for exact pinned operations in the declared local/container environment, using existing provider and slice A attempt/evidence contracts. Enforce reviewed scope, destinations, limits, timeout, cleanup, integrity, no moving latest reference, and exact actual environment fingerprint. Checks that can implicitly pull pass the installation guard. Append admitted/completed attempts with redacted output, selected version/integrity, approval reference for setup, and independently authorized feasibility result; installation success alone never proves adapter feasibility. Reject stale/mismatched completion as current readiness while preserving history. Produce actionable blockers for offline source, checksum mismatch, wrong environment, prompt/unsupported setup, and timeout. Cover permitted local/container and failure paths with high-signal integration tests using a deterministic runner.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
