---
id: task_054_001_002
title: Bind exact candidate receipts to bounded review admission and publication
tier: task
status: completed
parent: feat_054_001
children: []
depends_on:
- task_054_001_001
owners:
- swe
skills: []
parent_rev: 9830d168dc54c580417b4caa90c3b81ecb3c3e1c
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Bind exact candidate receipts to bounded review admission and publication

## Parent Feature

[feat_054_001](../../features/2_active/feat_054_001.md)

## Depends on

- task_054_001_001

## Acceptance criteria
- Candidate identity includes source SHA, freshly observed target SHA, prospective result commit/tree, review URL/identity and generation, approved profile ID/argv/coverage/owner/approval revision/timeout, and effective runtime/dependency/import identity. Store additive immutable/JSON-safe receipt fields in the existing action/incident operation records; no second ledger or weaker fallback.
- Preflight feasibility, candidate board scan and exact material identity precede reservation/spawn. Reserve once under the same top-level claim and incident-wide finite allowance. Only an exact matching successful receipt may be reused; material changes require fresh bounded admission. Unknown or legacy evidence fails closed.
- Re-read source, target, profile, authorization and runtime/dependency identity after checks and immediately before publication. Any drift refuses the push/acceptance. Deterministic failure of the same material remains fenced after restart, duplicate callback and A-B-A changes; corrected material can run only within the remaining allowance. Keep transient backoff, timeout, interruption and exact settlement semantics.
- Source publication and recovery return typed product-failure, fixture/environment, timeout, conflict and unavailable reasons with finite owner action; no duplicate review or force push. Real temporary Git fixtures prove changed target red, matching success reuse, drift refusal and restart behavior. Focus tests/test_review_publication_safeguards.py, tests/test_review_rebase.py and tests/task/test_incident_budget.py.
- Reconcile cascade/DESIGN.md REQ-REVIEW-PUBLISH-001 and DEC-REVIEW-PUBLISH-001 with actual receipt/claim/runner behavior and normal, drift, timeout and restart Mermaid flow. Keep cascade/task/DESIGN.md authoritative for incident/attempt policy. Extend the existing cascade-teams-code validator/profile/reservation/publication nodes under element.component.teams and cascade-team-components; cascade-task-code changes only for actual budget/admission symbols. Update model.dsl, views.dsl and workspace.contract.json in the pinned source workflow. Verify source contract, render, context-to-Code/Level up/deep links/source paths, stale symbols, warm cache and bounds; record results and gaps. Context and containers unchanged for unchanged runtime/persistence boundaries.


## Files likely touched

TBD.

## Implementation notes

## Purpose
Bind validator admission and durable success/failure evidence to the exact candidate, then consume that evidence at source publication. Reuse the existing action/review records and Task-owned incident allowance.

## Skills

_(none)_

## Test plan

Run focused production-adapter Git/review regressions in tests/test_review_publication_safeguards.py, tests/test_review_rebase.py and tests/task/test_incident_budget.py; record commands, outcomes, source contract/render/navigation evidence, and any gaps.

## Out of scope

Human forge protection or merge authority, a new ledger or allowance, and actual merged-revision CI policy belong outside this Task.
