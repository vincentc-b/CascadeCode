---
id: feat_054_001
title: Validate exact merge results with isolated fresh checks
tier: feature
status: completed
parent: epic_054
children:
- task_054_001_001
- task_054_001_002
- task_054_001_003
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: bb26a5c88b911e3ecbfe2b7682565225301ef018
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
approved_at: '2026-11-27T20:58:47.001398+00:00'
---
# Validate exact merge results with isolated fresh checks

## Parent Epic

epic_054

## Scope

# Validate exact integration results with fresh bounded checks

## Outcome
A green source branch cannot establish a healthy Feature-to-Epic or Epic-to-trunk integration. Bind admitted checks to source SHA, freshly observed target SHA, prospective result commit/tree, review identity/generation, approved validation profile and runtime/dependency identity. The same contract is consumed by pre-publication/acceptance and later actual-merge verification.

## Scope and owners
Own cascade/review_validation.py, review_rebase.py and their team_review_recovery.py admission interface; coordinate additive receipt fields with review.py/tracking.py. Reuse existing action/review evidence and incident budget, not a second ledger. Build isolated disposable exact-tree validation using production Git paths; retain real operator and team worktrees unchanged. Include existing physical board scan before validators; the next feature strengthens semantic/history checks.

## Acceptance criteria
1. Real Git fixture: source checks green, target gains incompatible Task boot contract, prospective integrated check fails at the intended assertion. Evidence identifies exact pair/result/profile and refuses publication or acceptance; no weaker profile fallback.
2. Target/source/profile/environment drift during or after checks invalidates evidence. Reuse only an exact matching successful receipt; material changes get bounded admission under the same incident allowance. Restart, duplicate callbacks and A–B–A failures do not repeat unchanged deterministic validation or duplicate reviews. Missing/unknown/conflicted merge result fails closed.
3. Preserve original argv/coverage, timeout, process-group cancellation and sanitized bounded diagnostics. Run from an isolated exact materialized tree; pin effective source/import paths and dependencies. Eliminate cross-run stale generated/bytecode input without deleting shared/operator caches. Equal-size same-second Python edits must demonstrate expected red assertion and then corrected exact bytes green; PYTHONDONTWRITEBYTECODE alone is insufficient because existing bytecode can still be read.
4. Distinguish product assertion failure, fixture/environment failure, timeout and unavailable evidence; report finite owner action. A fixture correction cannot weaken product assertions or hide the failed assertion.
5. Squash/rebase/stacked delivery cannot equate ancestry or source-only CI with accepted result proof. Observe actual accepted merge identity separately; exact merged-revision CI remains a later consumer's obligation. Do not change human forge protection/merge authority.
6. Keep Task delivery behavior intact; add focused production-adapter regressions around tests/test_review_publication_safeguards.py, test_review_rebase.py, test_late_repair_convergence.py and incident-budget tests. No full-suite mandate.

## Design ownership
cascade/DESIGN.md owns review receipt/profile/isolation contract, extending REQ-REVIEW-PUBLISH-001 and DEC-REVIEW-PUBLISH-001; cascade/task/DESIGN.md retains incident/attempt authority. cascade/workspace/DESIGN.md owns disposable checkout lifecycle if its public interface changes. Integrated views: cascade-supervisor-components and cascade-team-components; cascade-teams-code owns validator profiles, operation reservation, physical source-board scan and publication under element.component.teams. Extend that existing owner rather than creating a Boss-owned validator or another review component. cascade-boss-code owns review orchestration only; cascade-task-code owns budget/admission and cascade-workspace-code owns materialization. Tasks must include these view/source-contract updates and normal, drift, timeout and restart verification in their acceptance criteria. The existing validate_publication_board node calls the Board-owned parse_doc schema boundary; preserve that ownership while extending candidate validation. Do not invent deployed containers. Add normal and drift/timeout/restart sequence in owning design. Root context/container have no new actor/runtime/persistence boundary.

## Architecture and delivery acceptance
Feature planners must copy affected architecture updates into Task acceptance criteria, keep one owner per stable requirement/decision, and reconcile actual source and DESIGN.md at delivery. Update the authoritative architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json} through the existing revision-pinned workflow; do not rewrite accepted snapshots. Integrated native custom Code views must name cascade.codeComponent; nodes bind real sourcePath/sourceSymbol/parent and correct declaration kind. Validate source contract, local pinned render, context → containers → component → Code, Level up/deep link/source opening, stale renamed/deleted symbols, warm-cache reuse and render bounds. Record measured results and gaps. Diagrams describe implemented behavior, not delivery history. Tests use real temporary repositories/worktrees and production adapters with scripted forge transport; no live forge mutation is required. Preserve human approval, existing Task validation, incident-wide budgets and accepted review lineage. No installation authority is granted.

## Diagram-impact inventory

| Level/view | Owner and change |
|---|---|
| cascade-landscape, cascade-context | Root DESIGN.md: same operator, forge and local supervisor. No new actor, external system or authority edge; verify against final diff. |
| cascade-containers | Root DESIGN.md: disposable Git checkout remains a local validation resource; no new deployed process, store or network path. Verify against final diff. |
| cascade-supervisor-components, cascade-team-components | cascade/DESIGN.md: Teams candidate/validator/publication collaboration with Task budget, Workspace checkout and Boss acceptance. Update changed relationships only. |
| cascade-teams-code | cascade/DESIGN.md: extend existing element.component.teams nodes for profile, operation, board scan, validator and publication, linked to real symbols. Board still owns parse_doc. |
| cascade-task-code | cascade/task/DESIGN.md: update only changed budget/admission symbols; Task retains incident and attempt authority. |
| cascade-workspace-code | cascade/workspace/DESIGN.md: add real checkout/cleanup symbols if the public Workspace interface changes. |
| cascade-boss-code | cascade/boss/DESIGN.md: update review orchestration consumers only; validator nodes stay with Teams. |
| Mermaid flow | cascade/DESIGN.md and affected child designs: show normal candidate, drift, timeout, restart and accepted merge observation. |

For changed views update the pinned model.dsl, views.dsl and workspace.contract.json as one proposal, without rewriting accepted snapshots. Verify native Code owner, semantic IDs, sourcePath/sourceSymbol/parent and declaration kind, source contract, local pinned render, context to Code, Level up/deep link/source opening, stale symbols, warm cache and render bounds. Record measured results and gaps in Task closeout.

## Data structures

- `ExactMergeCandidate`: immutable source ref/SHA, freshly fetched intended target ref/SHA, Git merge disposition, and prospective result commit/tree SHAs. The private checkout path is an execution resource, not part of reusable material identity. Missing objects, unknown result or conflict has no successful proof.
- `ExactValidationMaterial`: canonical source, target and result commit/tree SHAs; original forge review URL/route and current generation; approved profile ID, exact argv, coverage, policy owner, approval revision and timeout; incident policy version; effective interpreter executable/version/digest, dependencies, import roots and source bytes. Its fingerprint excludes clocks, temporary paths, usage and diagnostics. Any changed field is new material, even when branch names match.
- `ExactValidationReceipt`: additive immutable fields in the existing action and Task incident-operation evidence: incident, live claim and unique operation IDs; canonical material fingerprint and inspectable fields; candidate/review/profile identities; settlement state, outcome/failure class, bounded sanitized diagnostics and charge. Only settled green with every field matching fresh observation is reusable. Deterministic red fences that exact material across restart and A–B–A changes. Legacy/missing fields cannot be inferred green.
- `AcceptedMergeIdentity`: separate original review identity/generation, intended target ref, actual forge accepted merge SHA and freshly observed target head. Squash/rebase can change commit or tree. Prospective validation never becomes actual merged-revision CI proof merely because acceptance occurred.

## API contracts

- Workspace's disposable candidate interface, if added, accepts exact fetched source/target object IDs and returns Git-produced result commit/tree plus owned cleanup handle or typed missing/unknown/conflicted evidence. It preserves operator and team refs, indexes, worktrees and caches; cleanup removes only invocation-owned resources.
- Teams' publication path materializes the candidate, scans its physical board, resolves one approved profile and reserves worst-case runtime under Task's current claim and incident-wide allowance before spawn. The runner retains exact argv/coverage, timeout, process-group cancellation and bounded diagnostics. Working directory, imports and dependencies resolve to candidate bytes; existing bytecode cannot mask equal-size same-second edits.
- The additive receipt reader returns `matching_green`, `same_material_fenced`, `admission_required` or typed `unavailable`/conflict after full canonical comparison. Only `matching_green` authorizes reuse. `admission_required` requires a new Task permit within remaining allowance. Producer and consumers use this matcher; review callbacks cannot substitute URL, ancestry, source-only CI or an older green generation.
- Before lease-protected publication and acceptance consumption, refresh source/target refs, result, review generation, profile/policy, interpreter/dependencies/import inputs, authorization and remote lease. Changed or unverifiable fields block reuse and publication pending bounded new admission or finite owner action. Green diagnostic output cannot waive drift.
- Tracking persists actual accepted merge identity from fresh forge evidence in the existing review generation. Review/Boss compare that SHA with intended-target integration evidence while preserving original URL/generation. Missing SHA, changed route, closed-unmerged review or absent target proof remains pending/refused. Later actual merged-revision checks remain a separate consumer obligation.

## Failure, drift and restart contract

| Evidence | Durable effect and finite next action |
|---|---|
| Product assertion red | Settle exact operation as deterministic failure, retain failing assertion and candidate identity, fence identical material; owner supplies changed material or authorized decision within remaining allowance. |
| Fixture/environment failure or unavailable input | Settle or conservatively retain reservation, name missing input; owner corrects fixture/environment or restores evidence without removing product assertion or downgrading coverage. |
| Conflict or unknown result | Do not spawn or publish; owner resolves conflict or refreshes missing Git evidence for the recorded pair. |
| Timeout, cancellation or interruption | Stop/reap local process group when possible; retain bounded diagnostics and conservative charge when settlement unknown; resume same claim/operation. |
| Source, target, profile, review, policy, authorization or runtime drift | Refuse reuse/push; retain prior receipt, refresh tuple and seek bounded new admission. Exhaustion uses existing incident escalation. |
| Interrupted push or duplicate callback | Re-read remote SHA/ancestry and original review generation; reconcile observed effect to existing action, never create a duplicate review. |

## Logic flow

~~~mermaid
flowchart TD
  A[Fresh source, target and review observation] --> B{Exact Git candidate?}
  B -->|missing, unknown or conflict| X[Typed refusal and finite owner action]
  B -->|yes| C[Private result checkout with exact bytes]
  C --> D{Physical candidate board valid?}
  D -->|no| X
  D -->|yes| E[Resolve approved profile and canonical material]
  E --> F{Durable exact material receipt?}
  F -->|matching green| H[Refresh identities and authority]
  F -->|same deterministic red| R[Retain failure and fence material]
  F -->|absent or changed| G{Task incident permit?}
  G -->|no| X
  G -->|yes| V[Run unchanged profile in candidate]
  V -->|red, timeout or interrupted| R
  V -->|settled green| H
  H -->|drift or unknown| X
  H -->|same exact tuple| I[Lease publish tested source SHA]
  I --> J[Reconcile remote effect and original review]
  J --> K{Actual accepted SHA on intended target?}
  K -->|no or unavailable| X
  K -->|yes| L[Expose identity to later merged-revision check]
  R --> M[Restart reads same claim, operation and material]
  M --> F
~~~

## Task breakdown

1. task_054_001_001 — Materialize and validate an isolated exact merge candidate. Git candidate, fresh runner, board scan, bytecode/import isolation, real-Git regression, Teams and conditional Workspace views.
2. task_054_001_002 — Bind exact candidate receipts to bounded review admission and publication; depends on task_054_001_001. Material identity, incident reuse/fencing, drift and restart, Teams and Task views.
3. task_054_001_003 — Track accepted merge identity and verify end-to-end review evidence; depends on task_054_001_002. Forge acceptance identity, shared receipt consumer, scripted-forge regression and final design/C4 reconciliation.

## Task 1 delivery contract and reconciliation

Task 1 merged as `acb1d5fd` and its canonical record is completed, but its primary `## Acceptance criteria` section still says `TBD`. Its detailed `## Acceptance` subsection and the contract below describe the planned scope; neither corrects the primary section. The supported `revise_task` tool refused the reconciliation with `task_054_001_001 cannot be revised while completed`. The lifecycle owner must provide a supported correction path before Feature sign-off. The Feature team must not bypass the Task guard through filesystem or ledger edits.

The merged implementation adds private real-Git candidate materialization and validation in `cascade/review_validation.py`, routes review publication through it in `cascade/review_rebase.py`, and extends the existing Teams Code view plus `cascade/DESIGN.md`. The focused real-Git fixture is in `tests/test_review_publication_safeguards.py`. These paths and the acceptance items below remain the Task 1 delivery evidence for Feature review; they do not constitute a correction to the canonical Task.

1. Use real Git to materialize the exact freshly observed source and intended target SHAs in an owned private checkout. Return the prospective result commit and tree or a typed missing, unknown, or conflict refusal. Preserve operator and team refs, indexes, worktrees and shared caches; clean only invocation-owned resources.
2. Scan the physical candidate board with Teams-owned `validate_publication_board` and Board-owned `parse_doc` before validator spawn. Malformed or duplicate lifecycle documents refuse validation.
3. Run the approved profile's original argv and coverage from exact candidate bytes with a finite timeout, process-group cancellation, bounded sanitized diagnostics, candidate-bound imports and dependency identity. Prevent existing generated or bytecode inputs from masking equal-size same-second edits without deleting shared caches. Classify product assertion, fixture/environment, timeout and unavailable evidence with a finite owner action.
4. Show a real Git source-green, incompatible-target, candidate-red fixture where the intended Task boot assertion fails; corrected exact bytes then pass. A fixture correction must retain the product assertion. Preserve Task delivery behavior and use focused production-adapter regressions in `tests/test_review_publication_safeguards.py` and `tests/test_review_rebase.py`.
5. Reconcile `cascade/DESIGN.md` execution, failure and recovery flow and `cascade/workspace/DESIGN.md` if the public checkout interface changes. Extend the existing Teams owner in `cascade-team-components` and `cascade-teams-code`; update `cascade-workspace-code` only for Workspace-owned public materialization. Keep Task budget and Board parser ownership. Context and containers remain unchanged only if the implemented diff adds no actor, deployed runtime, persistent store or external path.
6. For every changed C4 view, update the pinned `model.dsl`, `views.dsl` and `workspace.contract.json` as one proposal. Verify real source symbols, declaration kinds, component parent and native Code navigation, pinned render, source opening, reverse and deep-link navigation, warm reuse and render bounds. Record measured checks, normal and failure/restart traces, design paths reviewed and unresolved gaps in Task closeout.

## Task 1 integration review

Reviewed the merged `acb1d5fd` source diff, `cascade/DESIGN.md`, and the pinned C4 `model.dsl`, `views.dsl` and `workspace.contract.json`. Candidate materialization, validation and publication remain under `element.component.teams` in `cascade-team-components` and `cascade-teams-code`; the implementation adds no Workspace public interface, Task budget symbol, actor, deployed container or persistence boundary. The package design links real source entries and describes normal, refusal and restart behavior. No further design edit was needed in this Feature planning turn.

On the Feature integration branch, `/opt/conda/bin/python3.12 -m pytest -q tests/test_review_publication_safeguards.py tests/test_review_rebase.py` passed 40 tests, and `/opt/conda/bin/python3.12 -m pytest -q tests/workspace/test_c4_source.py` passed 14 tests. `git diff --check` passed. Pinned render and browser navigation, exact receipt/restart behavior, actual accepted identity and final integrated review remain in the Task 2 and Task 3 delivery gates. The canonical Task 1 primary acceptance defect remains open as stated above.

## Task 2 integration review

Reviewed merged Task 2 source in `cascade/review_validation.py`, `cascade/review_rebase.py`, `cascade/team_review_recovery.py` and `cascade/task/incident_budget.py` against the Feature acceptance. Candidate board inspection and complete material identity precede Task-owned reservation. The Teams receipt matcher reuses only a settled matching green operation, fences deterministic red for identical material, and treats incomplete or reserved evidence as unavailable. Publication refreshes material and remote heads before the lease-protected push. The implementation retains the existing incident allowance and review action rather than adding a ledger.

Reviewed `cascade/DESIGN.md`, `cascade/task/DESIGN.md` and the pinned C4 `model.dsl`, `views.dsl` and `workspace.contract.json` against that diff. New material inspection, receipt matching and review identity nodes remain under `element.component.teams` in `cascade-teams-code`; Task retains the budget node. No Workspace public interface, Boss validator owner, actor, deployed runtime, persistence store or external path changed. The package design's publication Mermaid flow reuses the `Receipt` node ID for both the matcher decision and publication evidence; Task 3's final design reconciliation must give those distinct nodes before completion.

On the Feature integration branch, `/opt/conda/bin/python3.12 -m pytest -q tests/test_review_publication_safeguards.py tests/test_review_rebase.py tests/task/test_incident_budget.py tests/test_review_recovery_journey.py tests/workspace/test_c4_source.py` passed 77 tests. `git diff --check` passed and the worktree was clean. This establishes focused candidate, receipt, budget and C4 source-contract behavior, not pinned render/browser navigation or actual accepted merge identity. Task 3 owns the accepted identity, shared consumer regression, final design/C4 reconciliation and navigation evidence. Task 1's canonical primary acceptance correction remains a separate lifecycle-owner prerequisite before Feature sign-off.

## Plan design review

Reviewed DESIGN.md, cascade/DESIGN.md, cascade/task/DESIGN.md, cascade/workspace/DESIGN.md, cascade/boss/DESIGN.md and cascade/board/DESIGN.md against the current review, validator, budget and pinned C4 Teams source. Existing documents show source-linked Teams ownership, Task budget authority, Workspace checkout boundary and Boss closeout. The current package design explicitly leaves exact merged-tree proof open. No DESIGN.md was edited during planning. Tasks must reconcile implemented code, execution/recovery diagrams, source contract, pinned render and navigation before delivery; this plan claims no unrun check.

## Risks & upward questions

A moving target requires fresh bounded admission. Squash/rebase may yield a different accepted commit than the candidate; observe it separately. Exhausted incident allowance uses the existing finite owner escalation rather than a new budget.

## Decision log

- `dec_001` · 2026-11-27 · Feature Architect · **Decision log**
  Chose Keep candidate validation and publication with element.component.teams; retain Task as the incident-budget owner and Workspace as the disposable checkout owner when its interface is used..
  Rationale: The existing validator, profile, reservation and publication nodes already live in cascade-teams-code. Extending them preserves one source of allowance and one review evidence lineage without adding a component or ledger.
  Honors: Epic diagram-impact inventory and existing Teams/Task/Workspace source ownership..

- `dec_002` · 2026-11-27 · Feature Architect · **Decision log**
  Chose Require an exact candidate validation receipt before publication or acceptance, and record the actual accepted forge merge SHA as a separate later identity..
  Rationale: The prospective Git result can differ from a squash or rebase merge, and ancestry or green source checks cannot prove the accepted target result. Separate identities let later merged-revision CI consume precise evidence without widening this feature into forge protection policy.
  Honors: Feature acceptance criteria for squash, rebase and stacked delivery; existing human forge merge authority..

## Closeout

Completed child work: `task_054_001_001` (Materialize and validate an isolated exact merge candidate), `task_054_001_002` (Bind exact candidate receipts to bounded review admission and publication), `task_054_001_003` (Track accepted merge identity and verify end-to-end review evidence).
