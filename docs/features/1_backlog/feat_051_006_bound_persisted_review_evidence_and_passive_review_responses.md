---
id: feat_051_006
title: Bound persisted review evidence and passive review responses
tier: feature
status: backlog
parent: epic_051
children: []
depends_on:
- feat_051_005
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Bound persisted review evidence and passive review responses

## Parent Epic

epic_051

## Scope

Close the confirmed scalar/payload bound gap against existing REQ-WARROOM-REVIEW-002 in cascade/war_room/DESIGN.md. This is a narrow completion of existing passive review evidence requirements, not a new general payload framework. Feature 5 retains delivery-consumer and cross-Feature recovery acceptance. Sequence afterward to reconcile shared review.py and final architecture against its integrated source.

At dcf55df7, record_feature_review_evidence caps rows but persists arbitrary-length check names and string generations; _review_evidence_projection passes generation strings through. The Architect's isolated 10,000-character reproduction is recorded in docs/epic_artifacts/epic_051_architect_feature_4_review.json.

## Required behavior and acceptance

- Define concrete serialized-size and scalar bounds for normalized persisted check evidence and its passive response projection, including aggregate/per-check generation values and check-name/status keys. Preserve ordinary supported string and integer generations, including zero. Keep the existing twenty-row presentation cap and explicit omitted/unavailable state.
- Preserve authoritative identity and equality: never make distinct check names or generations equal through truncation. Oversized or malformed authoritative evidence must remain an explicit bounded unavailable/refusal prerequisite; it cannot become empty-green, verified, fresh, or permission to admit repair. Trace actual health, admission and postcheck consumers before choosing the policy. Do not weaken exact-head/check-generation verification.
- Bound passive reads of legacy persisted observations and the repair-request/verification-postcheck fallback sources without rewriting history from GET. Board, room and open-review APIs must agree. GET/polling must perform no forge, lifecycle, repair or provider work.
- Reuse existing normalization, review registry and projection surfaces; no new store, scheduler, general CI system, dependency installation or deployment.
- Extend focused production-path persistence and API tests: boundary/over-limit input, Unicode serialized byte sizes, same-prefix distinct identities, long string and integer generation handling, omitted rows, unavailable persistence, legacy/fallback payloads and unchanged ordinary behavior. Assert bounded serialized output and unchanged authoritative comparisons. Reuse existing tests; avoid redundant exhaustive harnesses.
- Run the relevant focused review-health, postcheck and War Room checks and reconcile the final integrated acceptance record. Keep existing lifecycle/architecture fixture failures and the full Recovery-gate timeout distinct from an isolated passing retry. Epic completion remains gated on final verification and publication.

## Diagram-impact inventory and Task contract

Context/landscape (cascade-landscape, cascade-context) and cascade-containers: root/shared owners verify unchanged actors, runtime, stores and isolation because normalization stays inside current review supervision and passive UI. Components (cascade-supervisor-components, cascade-team-components, cascade-war-room-components): shared/Watchdog/War Room owners reconcile producer-to-registry-to-reader and refusal behavior. Code: cascade-watchdog-code owns record_feature_review_evidence and reconcile_open_review_health; cascade-dashboard-code owns feature_review_views and projection/read entry points. Review cascade-war-room-http-code for API behavior and cascade-feature-code/cascade-task-code for identity/fence consumers only if affected. Model/contract descriptions currently acknowledge the scalar gap and must be reconciled after the fix. Add native source-linked nodes only where significant implementation responsibilities require them.

Tasks must name owning designs, exact source symbols, view keys and update/no-change reasons across all levels. Review root DESIGN.md, cascade/DESIGN.md, cascade/watchdog/DESIGN.md and cascade/war_room/DESIGN.md plus changed interface consumers. Keep REQ-WARROOM-REVIEW-002 in its single owner. Supplementary flows must trace normal persistence/read and oversized or legacy evidence/refusal across restart, including action/postcheck fallbacks. Keep proposed policy in work records until implemented.

Validate source contracts and declaration kinds/ownership, bounded pinned rendering, actual context-to-container-to-component-to-Code Explore, Level up, deep-link restore and pinned-source opening for changed paths. Check stale/deleted symbols and warm artifact reuse without per-view process startup or relaxed bounds. Record actual checks and limits in closeout; preserve accepted snapshots. Epic Architect owns final integrated revision-pinned publication.

## Sequencing and limits

Depends on feat_051_005. Use the smallest implementation-plus-verification Task breakdown; final architecture reconciliation belongs in delivery acceptance, not a separate cleanup project. No accepted child is reopened, no Feature 5 Task is silently expanded, and no new product requirement is introduced. Escalate any necessary shared-contract expansion through the amendment protocol.

## Data structures

TBD.

## API contracts

TBD.

## Logic flow

Feature planning must trace normalization → bounded persistence → passive projection, plus oversized/legacy evidence refusal and restart, against the production consumers before Task sign-off.

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
