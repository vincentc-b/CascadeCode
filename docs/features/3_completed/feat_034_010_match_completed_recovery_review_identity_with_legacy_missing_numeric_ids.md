---
id: feat_034_010
title: Match completed recovery review identity with legacy missing numeric IDs
tier: feature
status: completed
parent: epic_034
children:
- task_034_010_001
depends_on:
- feat_034_009
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 5c04eb34893a3e1800a278ecff123ad56131e3b2
created: '2026-11-10'
updated: '2026-11-10'
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
approved_at: '2026-11-10T18:39:58.570224+00:00'
---
# Match completed recovery review identity with legacy missing numeric IDs

## Parent Epic

epic_034

## Scope

Correct the remaining Feature F audit incident investigation_90d4c50f3e8326ebc96bc0186bbb96a5 after Feature I integration. Preserve completed I and F. No diagram change: this is confined to existing audit identity reconciliation, without new stores, services or access grants.

At owned Epic revision 24956e36977468f8cef6e3eb2ba8fcedafa54016, I's _completed_resolution_execution requires string equality for both review_id and review_url. The actual retained admission action resolution:v1:e58059ef6a24760191f4653a01e6bf7ebd50260509f8edc865db5067158754ac has review_id='218'; the identical completed execution recovery has review_id=null. Both contain https://github.com/vincentc-b/CascadeCode/pull/218, and the completed execution binds owning_team.work_id and affected_work_id to feat_034_006 with completion reason review_health_restored. A read-only probe executing the integrated helper against actual persisted rows returns false. Changing only the missing ID in an in-memory control to '218' returns true. No persisted state was changed. The existing regression fixture fills both IDs and misses the production shape. Deployed product checkout still lacks I's completion helper; deployment alone will therefore not cure this remaining mismatch.

Acceptance:
1. Reproduce the actual null numeric ID plus matching review URL, exact action ID, owner and authoritative completed reconciliation using persisted-store integration coverage, without copying unrelated production data or credentials.
2. Resolve equivalent review identities using the authoritative review registry and an exact recognized forge URL when numeric ID is absent. Require exact action and owner identity and completed review_health_restored evidence. An absent optional numeric ID is distinct from an explicit conflicting ID. Do not treat a closed review alone or matching number in a different repository/forge as completion.
3. Suppress only the resolved historical admission; retain genuine live/failed/unrelated actions and conflicting owner, URL or supplied numeric ID evidence. Missing/malformed/ambiguous identities and unreadable stores must remain unresolved or unavailable as appropriate, never silently healthy.
4. Repeated projection is read-only and idempotent. Preserve all admission/recovery history and I's terminal-parent eligibility fix. No raw sidecar changes, completed-child retries or lifecycle resets.
5. Validate the narrow identity boundary through the real collector/observation path, including the actual legacy shape and explicit conflict/unavailable controls. Record exact checks, publish through canonical review, and after accepted integration request authoritative reassessment of the assigned F case. Distinguish integrated code from deployed runtime and do not claim success before current authoritative observation.

## Data structures

Reuse resolution_actions.json admission request, executions.json actions and completion_reconciliation, and reviews.json owner-to-review registry. No schema migration. Missing numeric ID is optional legacy evidence only when a complete, recognized repository-qualified review URL and registry prove the same identity; supplied conflicting evidence remains a mismatch.

## API contracts

Keep existing public audit APIs. Refine the internal completed-recovery identity join to compare normalized, registry-validated identities while retaining exact action_id and work ownership checks. Internal signatures may carry the already-read review registry as needed. Reads failing or returning ambiguous evidence must propagate unavailable/unresolved status. No new mutation endpoint.

## Logic flow

Resolve admission and recovery review identities against the same authoritative registry; reject explicit conflicts or ambiguous/missing identity; require exact action and owner plus completed reconciliation; omit only the proven-resolved reference. Leave history unchanged and preserve unrelated references.

## Task breakdown
- task_034_010_001

One focused SWE implementation and persisted-store regression slice in an isolated task worktree, followed by independent review and canonical publication. Do not dispatch before this corrective feature's own review and human approval under epic criteria 17–18.

## Risks & upward questions

Production runtime currently predates I; accepted correction and deployment are separate prerequisites. Avoid permissive URL guessing, number-only identity, or treating every terminal feature as healthy. Historical reconstruction and architecture acceptance remain H/epic concerns, outside this repair.

## Decision log

None yet.

## Closeout

Completed child work: `task_034_010_001` (Reconcile completed recovery review identity for legacy missing IDs).
