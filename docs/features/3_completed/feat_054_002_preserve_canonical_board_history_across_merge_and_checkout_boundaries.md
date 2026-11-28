---
id: feat_054_002
title: Preserve canonical board history across merge and checkout boundaries
tier: feature
status: completed
parent: epic_054
children:
- task_054_002_001
- task_054_002_002
- task_054_002_003
- task_054_002_004
- task_054_002_005
depends_on:
- feat_054_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: bb26a5c88b911e3ecbfe2b7682565225301ef018
created: '2026-11-27'
updated: '2026-11-28'
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
approved_at: '2026-11-27T20:58:47.932167+00:00'
---








# Preserve canonical board history across merge and checkout boundaries

## Parent Epic

epic_054

## Scope

# Preserve canonical board history across merge and checkout boundaries

## Outcome
Every publishable prospective result, accepted target and newly admitted integration checkout has one authoritative physical record per work ID, with valid hierarchy and exact accepted terminal/cancellation history.

## Scope and owners
Extend review_validation.validate_publication_board, board parse/store interfaces, workspace.branch_synchronization guarded merge and integration_worktree/closeout provisioning. Consume the exact result identity from feat_054_001. Reuse resolve_mutation_owner and existing terminal provenance; merged projection rank never authorizes selection or deletion. Canonical tracking/product roots remain distinct.

## Acceptance criteria
1. Scan all lifecycle columns in the actual candidate tree, including malformed documents/symlinks/duplicates and identity/status/column inconsistencies. Validate parent/child identity against the applicable pinned physical or split-root ownership contract; absent cross-root evidence is unavailable, not silently omitted or treated as permission to rewrite.
2. Reproduce divergent merge reintroducing stale backlog Feature copies alongside completed copies; refuse before publication/merge acceptance or new Epic checkout registration. Normal read projection tolerance cannot substitute for physical validation.
3. Compare accepted terminal provenance to the candidate: retained specifications and terminal descendant records cannot disappear, revert to an open copy, or lose cancellation reason/timestamp/cleanup outcome and exact accepted parent feedback/disposition. Preserve unrelated specs. Legitimate managed activation pointers use existing lifecycle rules; do not require arbitrary source/target byte equality across allowed transitions.
4. For duplicate/conflicting history return exact IDs/paths, relevant revisions, canonical owner and supported repair prerequisite. Any proposed cleanup is previewed and authorized through existing owner path; never silently delete by column preference. Validate repaired candidate independently before it can become publishable.
5. Real temporary Git tests cover clean/invalid merge results, split roots, squash/rebase and stacked histories, cancellation and moved records, repeated delivery, and target movement. Refused checkout creation leaves registry/branches/checkouts unpoisoned; final accepted physical boards have no duplicate IDs or history loss. Missing/stale proof cannot be reused for a new target.
6. Preserve existing guarded Task/Feature/Epic merge and retirement authority. Bounded failure preserves operator and team work; no reset, force push or speculative repair of another owner's checkout.

## Design ownership
cascade/board/DESIGN.md owns physical schema/identity invariants (REQ-BOARD-001); cascade/DESIGN.md and element.component.teams/cascade-teams-code own the validate_publication_board caller and exact review-validation boundary; cascade/workspace/DESIGN.md owns mutation/provisioning and terminal history (REQ-WORKSPACE-OWNER-001, REQ-WORKSPACE-RETIRE-001); cascade/boss/DESIGN.md links closeout consumer implications. Update cascade-board-code, cascade-teams-code, cascade-workspace-code and cascade-boss-code with real validator, owner resolver, provisioning and guarded merge symbols; update parent component relationships if needed. Add candidate → scan → history proof → admit/refuse and restart sequence in the owning design. Higher-level actors and runtime containers remain unchanged.

## Architecture and delivery acceptance
Feature planners must copy affected architecture updates into Task acceptance criteria, keep one owner per stable requirement/decision, and reconcile actual source and DESIGN.md at delivery. Update the authoritative architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json} through the existing revision-pinned workflow; do not rewrite accepted snapshots. Integrated native custom Code views must name cascade.codeComponent; nodes bind real sourcePath/sourceSymbol/parent and correct declaration kind. Validate source contract, local pinned render, context → containers → component → Code, Level up/deep link/source opening, stale renamed/deleted symbols, warm-cache reuse and render bounds. Record measured results and gaps. Diagrams describe implemented behavior, not delivery history. Tests use real temporary repositories/worktrees and production adapters with scripted forge transport; no live forge mutation is required. Preserve human approval, existing Task validation, incident-wide budgets and accepted review lineage. No installation authority is granted.

## Data structures

The implementation may choose names, but these values are required at its boundaries:

- A physical board inventory binds the product repository identity/root, tracking repository identity/root, candidate checkout root and exact `ExactMergeCandidate(source_sha, target_sha, result_commit, result_tree)` revision to each ID, path, tier, parent, children, status, column and parsed terminal/cancellation fields. It records malformed entries and symlinks as evidence.
- A typed refusal classifies malformed, duplicate, hierarchy, history, evidence_unavailable or target_changed; it carries affected IDs and paths, source/target/result/accepted revisions, canonical mutation owner when established, reason and supported owner action. Unavailable split-root evidence is distinct from an invalid candidate.
- A history proof binds Feature 1's exact candidate tuple and `ExactValidationMaterial` fingerprint (review route/generation, approved profile, policy and runtime/dependency identity) to the actual accepted merge SHA, observed intended target head, target repository/branch identity, canonical product/tracking roots and required retained terminal descendants. A proof for one target revision cannot authorize another. Existing Git, board, review and cancellation records remain the stores of record; do not add a second ledger.

Board read projections may rank copies for display; no rank selects a physical survivor or authorizes cleanup. Legitimate managed activation pointers follow the current lifecycle contract.
## API contracts

1. `materialize_exact_merge_candidate` and `inspect_exact_validation_material` supply the exact source/target/result commit/tree and pre-spawn physical board check. The publication boundary inspects the actual exact candidate tree before validator admission, returns a physical inventory or a typed refusal, and performs no board mutation. It checks every lifecycle column, including unexpected or cancelled-copy locations, without skipping malformed entries.
2. A history comparison consumes that inventory, pinned accepted target and canonical split-root ownership evidence. It proves retained specifications, terminal descendants and exact cancellation fields plus matching parent feedback/disposition. Missing ownership/provenance is unavailable; conflicting physical records are invalid.
3. Guarded Task, Feature and Epic merge paths and new integration checkout/closeout paths consume a fresh proof for their exact source/target/result. `match_review_validation_receipt` and `matching_exact_result_receipt` may reuse only the matching settled green receipt; missing, red, incomplete or changed material is not approval. They preserve current approvals, leases, validation budget, review lineage, mutation-owner and retirement gates. Refusal precedes publication or checkout registry/branch admission and leaves owner work intact. Re-read the product target head and tracking owner before the accepting mutation; a changed revision invalidates the earlier proof and requires a new candidate and bounded admission.
4. Repair requires an owner-scoped preview and existing authorized mutation path, followed by an independent candidate scan and proof. The validator never deletes or chooses a copy by column preference.
## Logic flow

~~~mermaid
flowchart TD
    Candidate[Exact source and target result] --> Scan[Scan every physical board record]
    Scan -->|Malformed, duplicate or mismatch| Refuse[Typed refusal with owner action]
    Scan -->|Valid| History[Compare pinned accepted terminal history]
    History -->|Missing, conflicting or unavailable evidence| Refuse
    History -->|Proven| Gate[Current review, merge or checkout authority gates]
    Gate -->|Current| Admit[Publish, merge or register exact result]
    Gate -->|Changed target or interrupted| Restart[Re-read exact revisions and proof]
    Restart --> Candidate
    Refuse --> Repair[Preview through canonical owner]
    Repair --> Candidate
~~~
## Task breakdown

1. task_054_002_001 — completed physical candidate inventory and identity/hierarchy validation. Its implementation merged as `e7fdeb1709f0ec861ef60a2bcdb769aabc9341c5`. The primary Task acceptance field remains `TBD`; its detailed execution contract is retained in this Feature plan pending a lifecycle-supported correction.
2. task_054_002_002 — completed accepted terminal/cancellation history proof; depends on 001. Its implementation merged as `703247c243a0cd624be481d7776ebc4fb2beadb6` and adds a pinned accepted-history proof, owner-routed refusal evidence, and Workspace/Teams design and Code-view entries.
3. task_054_002_003 — completed guarded Task/Feature/Epic merge and publication wiring; depends on 002. Its corrected branch includes `a0b17d6add649cd7c2d8e2f8ca470a72edfc584c`, and the canonical integration merge is `f85dbfda1c8ef7c8619a07bfa2e6d44a28ef9b19`. Supervised child final validation reported 52 passing scoped tests in 43.61 seconds. Final combined verification remains Task 005 work.
4. task_054_002_004 — completed integration checkout and closeout admission; depends on 002. Its implementation merged as `51fae3af3c0f2fa241b3f8cc908f55620b684a72`, including refused provisioning cleanup and target-fenced closeout proof.
5. task_054_002_005 — completed final validation and stale Epic model-key fixture correction. The supervised child validated `6778d9365e41205b666bc64441e8fe2ba2027f65` against Feature base `6a0cb490136b72e1f1dae6fd180f465e4a85c5b0` (71/71). The canonical feature-branch integration commit is `e86ee23853eec5d101d67d9bfad5b1e95fd66207`, and the completed Feature record is `0232826f6a9616cd700215b59bf9310196621cc3`.

Task 002–005 specifications carry their own acceptance criteria and tests. Task 001 is completed, but its primary acceptance field remains `TBD`; the supported `revise_task` path did not allow revision after activation. Its detailed contract in this plan does not correct the primary Task field. A lifecycle owner must reconcile that field through a supported path before Feature completion. The final task reviews Tasks 001–004 against the Feature acceptance before closeout.

### Diagram impact inventory

| Level / view key | Owner and source entry points | Required change and verification |
|---|---|---|
| Context: cascade-context | cascade/DESIGN.md; existing people/systems | No new actor or external dependency in this diff; confirm existing responsibility links remain accurate (005). |
| Containers: cascade-containers | cascade/DESIGN.md; supervisor and local board/Git boundaries | No new process or data store; verify persistence and tracking/product boundary wording (005). |
| Components: cascade-supervisor-components | cascade/DESIGN.md and Board/Workspace/Boss child designs | Trace validator → history proof → guarded merge/provisioning/closeout relationships; update any changed component links (003–005). |
| Code: cascade-board-code, cascade-teams-code | cascade/board/DESIGN.md and cascade/DESIGN.md; parse_doc, validate_doc, list_board, validate_publication_board | Source-link scanner and physical identity contracts with correct declaration kinds and model/contract IDs (001, 002, 005). |
| Code: cascade-workspace-code | cascade/workspace/DESIGN.md; resolve_mutation_owner, merge_lifecycle_source, create_integration_worktree, prove_terminal_retirement, create_verified_trunk_workspace | Show exact owner/proof, guarded merge, registration and restart paths with source symbols (002–005). |
| Code: cascade-boss-code | cascade/boss/DESIGN.md; merge_task_branch, try_complete_feature, Epic closeout consumers | Show accepted-result and terminal-history gate consumption without implying Boss owns board schema (003–005). |
| Behavior: owning DESIGN.md Mermaid flows | Board, Workspace, Boss and package publication docs | Candidate → physical scan → history proof → admit/refuse; normal, failure and restart with Git/registry/Markdown state (001–005). |

Architecture edits target architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/model.dsl, views.dsl and workspace.contract.json through revision-pinned publication. Validate source contract, local pinned render, context → containers → components → Code, Level up/deep links/source opening, stale symbols, warm-cache reuse and render bounds. Do not rewrite accepted snapshots.
### Task 005 child handoff before canonical merge

The Task team reports final validated deliverable `6778d9365e41205b666bc64441e8fe2ba2027f65` against refreshed Feature base `6a0cb490136b72e1f1dae6fd180f465e4a85c5b0`. The branch diff corrects `tests/board/test_validate.py` to reject an illegal Epic `reviewer` model key while retaining valid `swe` support. The canonical integration branch is at `25db3169`; this report is child evidence, not a merged Feature result.

The child reports a scoped pre-commit gate of 67 passed and pinned render 1 passed on its earlier pair. The earlier browser journey passed context → containers → components → Code, Level up, deep-link and pinned-source opening, including the refreshed documentation panel. The refreshed final supervised gate passed 71/71 in 108.00 seconds on the exact deliverable/base pair. An exploratory browser run on that pair passed Code navigation, deep links, source opening, Level up and warm-cache checks, then found empty content at the later refreshed documentation-panel text assertion; a complete browser pass on the refreshed pair is not established. Cold render was 64.575 seconds and warm cache reuse 0.131 seconds across 25 views, 326 elements, 413 relationships and 25 SVGs within the stated 180-second and resource bounds. The earlier nested-validator timeout did not reproduce. Its final design/source review covered `cascade/board/DESIGN.md`, `cascade/DESIGN.md`, `cascade/workspace/DESIGN.md`, `cascade/boss/DESIGN.md`, Board physical scan/parser, Teams publication/history proof, Workspace merge/admission/retirement, Boss consumers and the pinned model/views/contract. No additional design edit was reported. Context and containers retain their actors, processes and stores; component collaboration and the Board/Teams/Workspace/Boss native Code nodes match the final child diff. The child traced normal, refusal and restart paths with exact candidate, target and owner checks and preserved state on refusal.

A broader exploratory combined suite on the earlier child pair reported 115 passed and 28 failed, mainly older activation fixtures blocked by current provider/child-work admission plus one stale preflight expectation. The refreshed child pair reproduced two legacy single-review closure fixtures blocked at provider preflight and the browser documentation-panel assertion above. These are unresolved exploratory results, not a green Feature suite. After canonical merge, recheck the exact integration tree and classify failures that affect the Feature acceptance boundary. Task 001's completed primary acceptance field still says `TBD` and requires supported lifecycle-owner correction before Feature completion. The final Feature Architect review must use the merged exact Feature revision; the interim `e130993c` receipt does not accept Task 005's code or this plan update.

## Risks & upward questions

Integration review after Task 002 merge: inspected `cascade/DESIGN.md`, `cascade/workspace/DESIGN.md`, `cascade/review_validation.py`, `cascade/workspace/integration_worktree.py`, the native Teams/Workspace Code-view changes, and the focused Task 002 diff. The history proof is present, but Tasks 003–004 still own accepting-boundary wiring and Task 005 owns the final architecture and real-Git journey. A focused run of `tests/test_review_publication_safeguards.py`, `tests/workspace/test_integration_worktrees.py`, and `tests/workspace/test_c4_source.py` passed 76 cases and failed `test_exact_candidate_real_git_red_then_equal_size_same_second_green`: its 20-second nested validation returned `timeout` instead of `product_assertion`. A later isolated rerun passed (1 case in 24.85 seconds), so the earlier timeout is not reproduced on the current branch; the combined suite has not been rerun. No design edits were made in this review; the added requirement, source links and normal/refusal/restart sequence agree with the Task 002 diff, while full render/navigation and accepting-boundary traces remain pending.

Task 003/004 accepting-boundary handoff at plan revision `48ea9553`: `merge_lifecycle_source` could repair a missing worktree during preflight, and checkout creation preceded registration. Task 004 now proves the pinned board before preparation and registration, retains a pre-existing branch, removes only an attempt-created branch still at the admitted base on refusal, and fences the closeout target. Task 003's guarded merge implementation is integrated. Task 005 must exercise the combined normal, refusal and restart paths on the final tree.

Task 003 final child handoff: the corrected branch reports pre-proof missing-checkout refusal, exact product/tracking owner and target rechecks, and real-Git split-root success. Its source contract passed; the pinned render/cache completed in 75.02 seconds. The browser journey passed context through Code, deep-link, Level up, and pinned source checks, then failed a later refreshed documentation-panel assertion. Two legacy reconstructed-design assertions for the older task_034 owner/baseline remain stale. These are child validation reports; the implementation is merged, and final Task 005 classification remains open. No accepted snapshot was rewritten.

Split-root evidence or accepted target provenance may be unavailable at an admission point. Refuse with the missing source and owner action; do not infer permission from merged projection rank. Merge, checkout and review state can move between inspection and mutation, so each accepting boundary must recheck exact revisions. No Epic contract amendment is currently required.

Planning design review at the initial plan revision: read cascade/board/DESIGN.md, cascade/workspace/DESIGN.md, cascade/boss/DESIGN.md, cascade/DESIGN.md and the pinned model/views/source contract against scanner, owner, merge and provisioning entry points. Tasks 001–004 subsequently changed those contracts; Task 005 owns final-diff reconciliation and records exact checks/gaps in its closeout.

Task 004 integration review: inspected `cascade/workspace/DESIGN.md`, `cascade/boss/DESIGN.md`, `cascade/workspace/integration_worktree.py`, `cascade/workspace/closeout.py`, `cascade/boss/epic_complete.py` and the model/views/source-contract diff in commit `042454ee`. Workspace now states pinned base, split tracking owner, pre-admission physical proof, refusal cleanup and restart behavior; Boss states the fetched accepted target history gate. No additional design edit was needed for this merged diff. Focused checkout refusal, closeout refusal and C4 source-contract tests passed 16/16 on integration HEAD `c1a1b4db` (3.71 seconds reported by pytest). Context and containers add no actor, service or store; component relationships retain Board/Teams/Workspace/Boss roles; Workspace and Boss Code nodes were updated. Full pinned render, browser journeys, combined final-diff tests and accepted-target evidence remain Task 005 work. Task 001's primary acceptance correction remains a separate lifecycle-owner prerequisite.

Additional integration verification: `python -m pytest -q tests/board/test_validate.py tests/workspace/test_c4_source.py` passed 25 and failed 1 in 2.19 seconds. The sole failure, `test_models_wrong_tier_key_fails_validation`, expects an Epic `swe` model key to raise `SchemaError`; current `cascade/board/validate.py` includes `swe` in the Epic model-key allowlist. This is a stale fixture outside the Task 004 admission diff, not proof of a history-protection regression. On integration HEAD `447aa1b1`, I reproduced the isolated failure (`Failed: DID NOT RAISE`, 0.32 seconds). `cascade/board/validate.py` explicitly includes `swe` in `_EPIC_STACK_MODEL_KEYS`; commit `bad2ccc3` added the current full-stack model contract, and `tests/war_room/test_brief_full_stack_defaults_e2e.py` uses Epic `swe` defaults. Task 005 should change the fixture to a genuinely invalid Epic model key, keep meaningful invalid-key rejection coverage, and rerun the focused and combined final checks against its exact tree. Do not remove valid `swe` support to satisfy this assertion or claim a full green suite before that correction.
Task 003 integration review after canonical merge `f85dbfda1c8ef7c8619a07bfa2e6d44a28ef9b19`: inspected `cascade/DESIGN.md`, `cascade/board/DESIGN.md`, `cascade/workspace/DESIGN.md`, `cascade/boss/DESIGN.md`, the changed `model.dsl`, `views.dsl` and `workspace.contract.json`, and the source entry points `prove_accepted_terminal_history`, `merge_exact_lifecycle_candidate`, `promote_epic_to_trunk` and `create_integration_worktree`. Source links and existing Board/Teams/Workspace/Boss ownership cover physical scan, accepted-history proof, guarded merge and checkout admission. Context and container views retain the same people, systems, processes and stores. The component view keeps these collaborators within the supervisor boundary; Code view changes add the lifecycle merge and Epic promotion entry points. The child reports a passing source contract and pinned render/cache check, plus partial browser navigation; Task 005 must run final exact-tree source, render, full browser, normal/refusal/restart and combined test checks, including the stale fixture and legacy assertion classification. No additional DESIGN.md edit is indicated by this integration review; final diff review remains open.

### Post-merge verification and remaining acceptance evidence

On completed Feature revision `0232826f6a9616cd700215b59bf9310196621cc3`, the implementation tree is the canonical Task 005 integration commit `e86ee23853eec5d101d67d9bfad5b1e95fd66207`. The merged `tests/board/test_validate.py` uses an illegal Epic `reviewer` model key while preserving valid `swe` support. `/opt/conda/bin/python3.12 -m pytest -q tests/board/test_validate.py tests/workspace/test_c4_source.py` passed 26/26. The full `tests/war_room/test_architecture_browsing_browser_journey.py::test_branch_architecture_is_pinned_navigable_and_refreshes_whole_snapshot` passed on this exact tree in 144.32 seconds, including the refreshed documentation panel. This does not erase the earlier child-pair empty-panel observation; the test reads the panel after the snapshot/SVG readiness check while the UI loads documentation asynchronously, so a timing-sensitive assertion is a plausible cause. No UI or test edit was made.

Final design review checked `cascade/board/DESIGN.md`, `cascade/DESIGN.md`, `cascade/workspace/DESIGN.md`, `cascade/boss/DESIGN.md`, the merged source entry points and pinned `model.dsl`, `views.dsl`, and `workspace.contract.json`. Context and containers add no actor, process, store or new isolation claim; the component boundary retains Board physical identity, Teams publication proof, Workspace admission and Boss consumption. Native Board, Teams, Workspace and Boss Code source links and declaration kinds passed the 14-case source contract. The owning designs describe exact candidate scan, accepted-history proof, target/owner drift refusal and restart against Git, board and registry state. No further design edit is indicated by the merged source diff. Task 005's pinned render, navigation/source opening and cold/warm measurements are child evidence on its validated pair; the merged browser journey above is exact-tree evidence.

The Feature completion transition preceded a final exact-revision Feature Architect publication, and the latest stored review covers `210d75a9` while Task 005 was still unmerged. Task 001's completed primary Acceptance criteria remains `TBD`; its detailed Feature contract and 41 board/publication plus 14 C4 checks do not correct that field. Both need their supported lifecycle owners to reconcile them. The earlier exploratory 115 passed/28 failed run is retained as child evidence; reported failures include legacy activation fixtures blocked at provider/child-work preflight, two single-review closure fixtures and a stale preflight expectation. The scoped 71/71 supervised gate is green, but the broader exploratory set has not been reclassified on this completed exact tree and is not claimed green.

## Decision log

- `dec_001` · 2026-11-27 · Feature Lead · **Publication board authority**
  Chose A physical candidate inventory and pinned terminal-history proof gate each accepting boundary; read projection rank cannot choose or delete a copy..
  Rationale: Read projections combine checkouts and can hide divergent physical copies. Exact result and target identity must be checked before publication, merge or checkout registration.
  Honors: REQ-BOARD-001; REQ-WORKSPACE-OWNER-001; feature acceptance criteria 1–4.

- `dec_002` · 2026-11-27 · Feature Lead · **History evidence and repair**
  Chose Reuse canonical Git, board, review and cancellation provenance; missing split-root evidence refuses admission and repair stays with the canonical mutation owner..
  Rationale: A second history ledger could drift from the accepted board. Existing owner and terminal-retirement gates already define safe mutation and recovery boundaries.
  Honors: REQ-WORKSPACE-OWNER-001; REQ-WORKSPACE-RETIRE-001; feature acceptance criteria 3–6.

## Closeout

Completed child work: `task_054_002_001` (Validate physical board identity in exact candidate trees), `task_054_002_002` (Prove accepted terminal and cancellation history), `task_054_002_003` (Guard lifecycle merges with physical board proof), `task_054_002_004` (Guard integration checkout and closeout admission), `task_054_002_005` (Verify end-to-end history preservation and architecture navigation).
