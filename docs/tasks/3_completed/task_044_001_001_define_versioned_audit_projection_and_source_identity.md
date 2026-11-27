---
id: task_044_001_001
title: Define versioned audit projection and source identity
tier: task
status: completed
parent: feat_044_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: b06beabcf813e4cddb4d312cd80cd95f29ffd5af
created: '2026-11-14'
updated: '2026-11-14'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Define versioned audit projection and source identity

## Parent Feature

feat_044_001 (frontmatter pins the current parent revision); through it, epic_044 projection and immutable-history constraints apply.

## Depends on

None.

## Acceptance criteria

- Define one versioned JSON projection schema for manifest, current, coverage and history summaries under the canonical product root. Expose typed/validated producer models or constructors that feature 002 can consume without importing War Room GET logic.
- Stable `source_ref` identifies one of the three existing recovery stores, a durable row key and, where needed, an `incident_history` ordinal. It never accepts an arbitrary path. Preserve occurrence, last attempted and last successful verification as separate fields.
- Modern current identity is valid only when `work_id`, `authoritative_generation` and `failure_class` are unambiguous. Legacy remediation records with `child_id`, `observed_child_sha` and `supervisor_id` remain historical/unverifiable with their original provenance. Malformed neighbor rows do not suppress valid rows.
- Bounded summaries carry source references and `detail_truncated` for large record fields; no raw provider prompts, credentials or hidden reasoning are copied.
- Document schema version, state transitions and source compatibility in the producer design/fixture location. Leave source ledger bytes untouched.

## Files likely touched

`cascade/watchdog/audit_projection.py` or a focused producer module, `cascade/watchdog/DESIGN.md` if a child design owns this boundary, and focused `tests/watchdog/` fixtures/tests.

## Implementation notes

Use existing regular-file/no-follow read helpers and recovery store shapes. Keep page/index representation compatible with feature 002's 50-row default, 100-row maximum, 1 MiB source-read and 256 KiB response budgets. Missing or oversized source content becomes coverage with a typed reason, not an empty healthy state.

## Skills

_(none)_

## Test plan

Use focused pytest fixtures with modern current and prior generations, all three stores, the six-field legacy shape, malformed adjacent rows and a large evidence field. Verify stable references and that source files are byte-for-byte unchanged.

## Out of scope

Candidate scheduling, atomic publication, dashboard GET, UI and recovery policy.
