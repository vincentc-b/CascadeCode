---
id: task_051_004_002
title: Expose authenticated repair action and review state in War Room
tier: task
status: completed
parent: feat_051_004
children: []
depends_on:
- task_051_004_001
owners:
- swe
skills: []
parent_rev: 0733fb8f15da227daad2bccfbb89027889c43734
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose authenticated repair action and review state in War Room

## Parent Feature

[feat_051_004](../../features/2_active/feat_051_004.md)

## Depends on

- task_051_004_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope and acceptance
Expose a narrow authenticated human POST for the existing team_supervision.request_feature_review_repair adapter. Validate Feature ID, stable request ID, reason/evidence, exact original open-review identity and caller scope; pass AuthenticatedHuman from the existing request verifier. Return the adapter's typed admission, queue acknowledgement, execution, refusal, verified and next-prerequisite fields without treating an HTTP acknowledgement as completion. Identical replay joins the same action; changed content, stale/duplicate requests, another writer, approval waits, cancelled or closed-unmerged reviews return the canonical typed prerequisite/refusal. Preserve the original branch, PR, comments and human merge policy. No new launcher or ledger.

Render the original PR URL, accountable Feature, implementation/delivery distinction, CI/feedback freshness and repair generation across board, open-review pane and room. Keep review-pending visibly awaiting review. Wire the explicit action to the POST and display its typed result, with polling limited to the read API. Exercise keyboard and stale-response behavior.

## Verification
Extend War Room route and JS tests and run a real Playwright browser transition through pending, red, admitted, executing, green/approval wait and verified states. Verify GET-only polling, attach and plan open cannot invoke providers, query forge authority or mutate lifecycle records. Cover split roots, missing policy, duplicate/stale request, unauthenticated caller, closed-unmerged and legacy completed-open review.

## Design handoff
Update cascade/war_room/DESIGN.md HTTP/action/browser interface and flow, plus parent/consumer links. Reconcile cascade-war-room-components, cascade-dashboard-code and cascade-war-room-http-code in model.dsl, views.dsl and workspace.contract.json with real source symbols, kinds, ownership and metadata. Record context/container no-change or updated edges; validate source contract, pinned render, navigation through Code, Level up, deep link and pinned source, including rejection and replay traces. Preserve accepted snapshots.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
