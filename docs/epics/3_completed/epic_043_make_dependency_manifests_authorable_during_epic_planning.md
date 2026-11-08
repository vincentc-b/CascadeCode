---
id: epic_043
title: Make dependency manifests authorable during epic planning
tier: epic
status: completed
parent: null
children:
- feat_043_001
- feat_043_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-07'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
plan_approved_at: '2026-11-07T23:40:31.773974+00:00'
---
# Make dependency manifests authorable during epic planning

## Intent

Prevent missing-manifest deadlocks by giving the owning Epic planning team a scoped, revision-safe way to record either an explicit no-dependencies declaration or a complete dependency manifest before sign-off, feature minting, or later guarded planning actions. Keep dependency declaration separate from execution authority: agents may describe required software and verification, but every installation or upgrade remains subject to the existing authenticated human approval boundary.

### Success criteria

1. The Epic Manager and Epic Architect can read and append a dependency manifest only for their own active Epic, using the canonical manifest schema and expected-revision protection; arbitrary sidecar or cross-Epic writes remain denied.
2. The same scoped planning surface supports an explicit none-required declaration with a complete target environment identity, so legacy active Epics can satisfy their next guarded planning action without fabricated dependencies or direct Python calls.
3. Manifest authoring grants no installation, upgrade, sudo, license, credential, or execution authority. Existing per-dependency authenticated-human approvals and trusted bounded execution remain mandatory and independently auditable.
4. Brief creation/activation and active-Epic planning expose missing_manifest as an actionable authoring step. The War Room and team prompt identify who may declare the manifest and do not present bootstrap review controls that require a nonexistent manifest.
5. Successful manifest creation refreshes canonical readiness and allows ordinary evidence-bound role sign-off and feature mint/dispatch without restarting or cancelling accepted work. Stale revisions, invalid environments, malformed dependency entries, completed/non-owned Epics, and duplicate submissions fail safely and idempotently.
6. End-to-end tests cover a legacy active Epic declaring none required, an Epic declaring real dependencies, stale concurrent writes, cross-Epic denial, preserved human-only installation approval, War Room guidance, restart, and the sign-off-to-feature-dispatch flow.

## Macro-architecture

### Scoped declaration contract

Expose read_dependency_manifest and write_dependency_manifest through the existing Epic planning tool registry and MCP catalog for epic_manager and epic_architect. Resolve the Epic identity and owning integration worktree from trusted planning context. The caller cannot select another Epic, root, sidecar path, authorizing actor, or execution capability. Feature, task, and Boss tool surfaces gain no manifest-authoring authority. Keep generic document/sidecar path guards restrictive.

Enforce the planning-role allowlist at execution as well as catalog exposure: the generic Epic dispatcher does not currently establish role authority for every registered tool. Bind role and owner from trusted context and reject caller-supplied scope/root/actor overrides and unknown fields in the runtime handler, including calls that bypass JSON-schema validation. Missing, boolean, negative, fractional, or string expected_revision values are invalid; do not inherit the canonical writer's optional revision argument as the public tool contract.

The read result contains the current canonical snapshot and manifest revision, or an explicit missing result with revision 0. The write takes the canonical manifest draft and a required non-negative integer expected_revision: 0 for creation, the current revision for an append. Manifest revisions are distinct from the Epic plan Git SHA. Do not require software readiness to read or author the declaration that establishes that readiness.

Reuse cascade.epic.dependency_manifests validation and append-only persistence under the existing dependency_state_lock. Reject malformed entries, duplicate dependency IDs, incomplete target environment identities, and invalid actual environment declarations before mutation. Require the current complete environment shape at the planning boundary, including for none_required, rather than silently accepting legacy identity defaults. Preserve legacy history reads and existing approval/evidence compatibility. Check the raw current-schema environment keys before compatibility parsing can fill legacy defaults, then require fully specified identities for the top-level target, every dependency target, and a non-null actual_environment. Preserve actual_environment=null as a valid unobserved declaration, and preserve independent per-entry target environments rather than forcing them to match the top-level display default.

The explicit no-dependencies path uses none_required=true and dependencies=[] with a fully specified target environment. An empty list alone is never a declaration. For real dependencies, retain canonical per-entry version/source/integrity, environment, installation scope/destination, cleanup, verification, and feasibility fields. A declared actual environment or verification recipe remains a declaration; it is not trusted execution evidence.

### Concurrency, authority, and readiness

Preserve the writer's current ordering: check expected_revision under the shared lock before comparing content. Identical content at the current revision returns the same snapshot without a new history entry. A replay with an obsolete expected_revision fails as stale even if its content matches; the caller rereads and retries deliberately. Concurrent authors cannot overwrite each other's revision. Completed or non-owned Epics, caller scope overrides, and path/symlink escapes fail without mutation. Resolve and verify the live owning worktree explicitly before persistence; the lower-level manifest resolver's fallback to trunk is not authorization to write there. Exercise a real owning-worktree fixture, including split target/tracking repositories, so tests prove both the destination and the canonical lock identity rather than relying only on single-root fixtures.

After a successful append or no-op, return JSON-safe canonical persisted data with manifest_revision and freshly computed software/bootstrap and plan-readiness projections. Keep the write and returned projection coherent under the existing re-entrant dependency-state lock using the same canonical lock root as other dependency authority operations; a concurrent append must not silently label another revision's readiness as the submitted revision. Reuse project_dependency_status rather than interpreting graph-only refresh_dependency_status as software readiness. Keep graph dependency status distinct from software-manifest readiness: a satisfied depends_on projection does not resolve missing_manifest. Preserve existing evidence-bound sign-off, approval, feature-mint, and dispatch gates. Real dependencies remain blocked until their existing human authorization and trusted verification requirements are satisfied.

Manifest edits must retain append-only audit history and existing binding-based approval/evidence invalidation rules. A declaration does not grant installation, upgrade, sudo, credential, license, bootstrap execution, or approval authority. No new executor or approval route is needed.

### User guidance and lifecycle

Use the shared dependency-status projection for actionable missing_manifest guidance in brief creation/activation, War Room, and active-Epic planning prompts. State that the owning Epic Manager or Epic Architect must read and declare the manifest through the scoped tools, then continue ordinary planning. Activation must allow the team to reach this authoring step; do not require a preexisting manifest before an active owner can create one.

When no manifest exists, suppress bootstrap-review, installation-approval, and execution controls that need a manifest. After declaration, show the canonical next blocker or ready state. None-required declarations do not need installation approval. Existing accepted work and the same run remain intact; restart reloads the persisted declaration and readiness without a second declaration or fabricated evidence.

### Verification approach

Extend existing boundary and lifecycle tests rather than duplicating schema unit coverage. Exercise the production planning dispatcher/MCP catalog, owning-worktree resolution, canonical projections, and normal lifecycle gates. Use isolated repository fixtures and the existing trusted-executor test harness; tests must not install external software.

The release matrix covers both planning roles; absent/read/create/append/no-op; stale concurrent writes and restart; malformed or incomplete declarations; cross-Epic and completed-Epic refusal; sidecar isolation; legacy active-Epic recovery; real dependency declarations remaining blocked before human approval and trusted evidence; and no new installation authority. One integrated scenario follows declaration through current-role sign-offs, ordinary human plan approval, feature mint, and existing dispatch. War Room/prompt tests cover missing-manifest guidance before and after activation and correct controls after declaration.

Baseline check on 2026-11-07: `python -m pytest -q tests/epic/test_dependency_manifests.py tests/epic/test_dependency_planning_gates.py::test_absent_manifest_blocks_all_entry_points_and_none_required_passes` produced 5 passed and 1 failed. The lifecycle case reached final plan approval, then failed with `ApprovalSelectionError: Agent configuration is missing`. Feature B must use an explicit supported provider-inventory fixture to exercise that final boundary; this baseline does not establish a passing end-to-end flow. No product code was changed during this planning check.

Architect review baseline on 2026-11-07: `python -m pytest -q tests/epic/test_dependency_operation_authority.py tests/epic/test_dependency_multiprocess_serialization.py tests/epic/test_dependency_status.py` produced 10 passed and 7 failed. All seven failures are in operation-authority tests: `_require_mutation_authority` in `cascade/epic/dependency_evidence.py` passes `entry.operation` (a string) to `require_installation_approval`, whose contract requires an `InstallationBinding`. This rejects approved admissions before dispatch/completion and prevents the five policy-denial cases from reaching their intended checks. This is an existing production call-site mismatch, not the provider-inventory fixture issue above. Feature B must make the minimal binding-preserving correction and pass these existing tests before claiming the real-dependency lifecycle acceptance; do not relax the approval checker or add an executor. No product code or dependency was changed during architect review.

## Cross-module constraints

Reuse cascade.epic.dependency_manifests and the existing dependency-state lock, planning MCP registry, War Room projection, evidence snapshots, and lifecycle gates. Do not add a parallel manifest store or infer none-required from an empty list. Treat manifest declaration as plan authorship and installation approval as a distinct human authorization. Preserve append-only history, optimistic concurrency, owning-worktree isolation, safe serialization, and existing accepted work. No automatic installation or dependency substitution is in scope.

Keep the implementation to the declaration boundary and its lifecycle guidance. Do not add a general dependency editor, package resolver, dependency upgrade, bulk migration, automatic none-required backfill, replacement bootstrap workflow, or generalized sidecar write permission. Reuse existing Python and JavaScript test tooling.

## Core dependencies

No cross-Epic prerequisites are declared; the authoritative lifecycle dependency projection is satisfied. Implementation uses existing manifest, lock, approval, evidence, registry, projection, and lifecycle modules already in this checkout. No new third-party package or installation/upgrade is proposed.

Read-only environment checks on 2026-11-07 found Python 3.12.8, pytest 9.0.3, and Node v20.20.2. These observations support the existing test plan but are not a canonical manifest, authenticated installation approval, or trusted dependency-readiness evidence.

Recovery status (2026-11-07): the human operator reported canonical manifest revision 1 with explicit none_required and satisfied live software/bootstrap readiness. Normal Cascade actions now confirm recovery: Epic Manager sign-off on revision 7019150 and both feature mints succeeded without bypassing dependency gates. No manifest or installation authority was exercised by this planning turn. The former missing_manifest blocker is resolved for epic_043; the product work still supplies the supported authoring surface for other Epics. Continue the existing activation run through current-revision role sign-offs and ordinary human plan approval/dispatch.

## Feature breakdown

- A: feat_043_001 — Scoped dependency manifest authoring for Epic planners.
- B: feat_043_002 — Actionable declaration guidance and complete planning recovery; depends_on: [feat_043_001].

Both sequential features were created through mint_feature on 2026-11-07 after operator recovery. Their persisted acceptance criteria and verification scope retain the architecture below. The earlier missing_manifest refusal is historical; both features are in backlog pending normal approval/dispatch.

### A. Scoped dependency manifest authoring for Epic planners

Deliver the guarded read/write tools, required revision contract, complete declaration validation, trusted scope/role binding, canonical persistence, and fresh readiness results. Include boundary integration tests for both roles, explicit none-required and real manifests, invalid input, stale/replayed/concurrent writes, owning-worktree and completed/cross-Epic denial, and unchanged installation authority. This is the smallest functional slice that lets an active planning team repair missing_manifest through supported tools.

Acceptance: success criteria 1–3 and the authoring/readiness safety portions of 5; the canonical write is immediately consumable by normal planning gates. No new third-party dependencies.

### B. Actionable declaration guidance and complete planning recovery

Depends on A. Deliver brief/activation guidance, shared War Room and prompt messaging, missing-manifest control suppression, and same-run refresh/recovery. Extend existing lifecycle and UI tests to prove none-required and real-dependency paths, restart persistence, preserved approvals/accepted work, and sign-off through normal approval, feature mint, and dispatch.

Acceptance: success criteria 4–6 in full, with no manual sidecar or direct Python workaround in the tested authoring flow. Feature B owns final cross-surface verification, the minimal operation-authority call-site correction identified in the architect baseline, and the supported provider-inventory fixture for normal approval/dispatch. Existing operation-authority tests must pass alongside the new authoring flow; no separate test-only feature.

## Open questions

No unresolved product-scope choice. The Epic Architect reviewed the canonical writer, planning dispatcher/registry, worktree guards, environment schema, dependency lock, readiness projection, and evidence-bound sign-off on 2026-11-07. The review is incorporated above: runtime role/input enforcement, validation before legacy defaults, coherent persisted-revision projections, owning-worktree coverage, and the existing operation-authority defect assigned to B. The two-feature architecture is accepted for implementation subject to these acceptance requirements; this review does not claim canonical role sign-off or a passing end-to-end baseline.

The canonical recovery question is resolved by the operator's revision-1 none-required declaration and successful guarded planning actions. No unresolved scope question remains. Both roles must sign the final current revision after feature creation and this status update. Epic Manager can sign only its own role; Epic Architect must independently review and sign through its role-bound tool. Normal human plan approval and dispatch follow without replacing the existing activation run.

## Decision log

- 2026-11-07 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-07 · Epic Manager · **Feature breakdown**
  Chose Deliver two sequential features: scoped manifest authoring, then declaration guidance and complete planning recovery..
  Rationale: The canonical store and gates already exist. Two slices cover the approved success criteria without a new dependency editor, package resolver, bootstrap workflow, or standalone test feature.
  Honors: Intent; success criteria 1–6; frugal-engineering and product-manager scope discipline..

- `dec_002` · 2026-11-07 · Epic Manager · **Macro-architecture**
  Chose Require revision-bound, own-active-Epic declaration through planning tools while retaining canonical concurrency semantics and all human execution approvals..
  Rationale: Missing-manifest recovery must be callable before software readiness. Declaration grants no execution authority. A current-revision identical write is a no-op; a stale expected revision fails before content comparison, matching the existing canonical writer.
  Honors: Success criteria 1–3 and 5; append-only history, owning-worktree isolation, and independent authenticated-human installation approval..

- `dec_003` · 2026-11-07 · Epic Manager · **Core dependencies**
  Chose Keep feature minting and final sign-off pending canonical manifest recovery for epic_043.
  Rationale: The current planning catalog has no manifest authoring tool, and mint_feature was refused with dependencies_not_ready (missing_manifest:manifest). A satisfied graph dependency projection is not software readiness; bypassing the gate via direct Python or sidecar mutation would undermine the approved contract.
  Honors: Success criteria 2, 3, and 5; canonical lifecycle state and authenticated-human approval boundaries.

- `dec_004` · 2026-11-07 · Epic Architect · **Macro-architecture**
  Chose Accept the two-feature architecture with runtime role enforcement, strict raw-input validation, explicit owning-worktree resolution, and coherent manifest-revision/readiness results..
  Rationale: The existing registry does not enforce every tool's role, the canonical writer permits omitted revisions, and environment parsing supplies legacy defaults. Dedicated scoped wrappers must enforce the new public contract without weakening legacy readers or generic sidecar guards. Persisted data and readiness must use the canonical dependency lock and JSON-safe projection.
  Honors: Success criteria 1–3 and 5; canonical concurrency, per-entry environment identity, owning-worktree isolation, and existing human-only installation authority..

- `dec_005` · 2026-11-07 · Epic Architect · **Verification approach**
  Chose Assign Feature B the minimal full-binding approval-call correction and require the existing operation-authority tests to pass before real-dependency lifecycle acceptance..
  Rationale: Architect baseline produced 10 passed and 7 failed. The production admission helper passes entry.operation to an approval checker requiring InstallationBinding, rejecting approved operations and masking policy-specific checks. Repair the caller while retaining the strict approval contract; this is separate from the manager's provider-inventory fixture failure and needs no new executor or test-only feature.
  Honors: Success criteria 3, 5, and 6; frugal-engineering reuse of existing high-signal tests; no expansion of execution authority..

- `dec_006` · 2026-11-07 · Epic Manager · **Core dependencies**
  Chose Close the historical missing_manifest delivery blocker after canonical operator recovery and continue the existing activation run with feat_043_001 followed by feat_043_002..
  Rationale: The human reported revision-1 explicit none_required and satisfied readiness; normal Epic Manager sign-off and both guarded feature mints succeeded. This fulfills the recovery condition in dec_003. Current-revision sign-offs must be renewed after plan updates, with each role signing only for itself, followed by ordinary human plan approval and dispatch.
  Honors: Human recovery instruction of 2026-11-07; dec_001 two-feature sequence; dec_003 canonical recovery condition; success criteria 3 and 5; preserved role, dependency, and human approval gates..
## Amendment log

_(none)_

## Implementation audit · 2026-11-08

Status: open; partial implementation in `999f79ef`, `b55abca2`, and `bc615b88`. The prior blanket completion claim is withdrawn. Preserve the active Epic plan and its child work; no acceptance criteria are waived.

- Scoped manifest authoring and the none-required → role sign-off → approval → Feature-dispatch path are implemented.
- The closure audit found an in-scope real-dependency defect: operation authority passed an operation string to an approval boundary requiring an InstallationBinding. `bc615b88` fixes this with `InstallationBinding.from_entry`, preserving exact approval and policy checks. All 11 dependency-operation authority tests now pass.
- Criterion 6 still needs complete acceptance evidence for real-dependency authoring through approved execution, concurrent public writes, both planning roles, target/tracking worktree separation, and guidance/activation/restart behavior. Passing the isolated authority suite does not establish that full lifecycle.

## Final direct delivery · 2026-11-08

Status: completed. Implementation through `a37f05ff` and preceding commits supersedes the earlier partial-completion audit. The operator explicitly requested implementation directly on main because the affected tool could not reliably implement its own repairs. No acceptance criteria are waived.

All acceptance criteria and the active plan's authority correction are implemented. The InstallationBinding mismatch is fixed in `bc615b88`. Manifest writers and human approvers now share the same dependency-state lock across worktree and trunk roots. Public planning tests cover both roles, real dependency declaration through human approval, bounded trusted execution, current-role sign-offs, ordinary plan approval and Feature dispatch; they also cover concurrent revisions, fresh-process reload, split target/tracking repositories, owning-worktree isolation, completed-owner refusal and guidance. Browser tests verify that missing manifests suppress controls that require a declaration. The none-required lifecycle remains covered separately. No installation, credential, license, sudo or execution authority is granted by authoring.

See `tests/test_epic43_acceptance.py`, `tests/test_planning_manifest_and_team_controls.py`, `tests/epic/test_dependency_manifest_authoring.py`, `tests/epic/test_dependency_operation_authority.py`, `tests/epic/test_dependency_multiprocess_serialization.py`, and `tests/war_room/test_dependency_review_ui.py`. Existing Feature and Task plans are retained as the work breakdown and reconciled to the implementation delivered directly on main.

Validation: the combined affected acceptance suite passed 164 tests; additional targeted crash, failure, and cross-process checks passed. This records scoped acceptance, not a claim that every unrelated repository test passes.
