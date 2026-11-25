# Controlled runtime exercise preflight

This is a read-only preflight for a later, separately authorized operational
exercise. No installation, drain, restart, deployment, credential use, fault
injection, remote publication, lifecycle mutation, or rollback was performed.
Proposed injection points below are not evidence that a fault occurred.

## Repository observation and target selection

The contributor environment was observed on 2026-11-25 UTC. With no
`tracking_repository` configured in `cascade.toml`, the current colocated
product and tracking root is `/home/ubuntu/dev/CascadeCode`, checkout `main`, at
`50681103e39327462025a5518236161cd31dd7fe`. It was not eligible as an exercise
target because `architecture/review-units.json` was modified. The Feature owner
checkout was `/home/ubuntu/dev/CascadeCode/.cascade/worktrees/feat_feat_048_003`,
branch `feat/feat_048_003`, observed historically at
`05b1296f6e3a4910347513d9b880a11bdce3a7b9`. That observation preceded later
Feature and Task integration and is not the final exercise target or integrated
revision. The documentation verification checkout is
`/home/ubuntu/dev/CascadeCode/.cascade/worktrees/task_task_048_003_003`, branch
`task/task_048_003_003`; it is not an installation source or operator trunk.

The historical implementation lineage visible here includes Task 001's repair
implementation tip `76f6eda05c14b2c99dd3bd4e17412bbf40a69b95` and integration record
`286081dd6a38823e180d6eea8989870276b1b356`, and Task 002's journey
implementation `85680656f799c8a9f27e1fc0c5ab1a780bef75ab`, relationship correction
`f238169dfcb8a32768fb5d13c9314a8b1a49de72`, and integration record
`856e1ac3055a7ba739df0f2b3e4c5083bf9c79e9`. These repository commits establish the
code under review, not an accepted operational review URL, authorized installed
artifact, or loaded worker. The later exercise must record full 40-character
accepted-review and integrated-target commits from its selected clean checkouts;
the implementation lineage above cannot fill either field.

The current contributor interpreter was `/opt/conda/bin/python`, importing
`cascade` from this Task checkout. That is validation-process provenance only,
not the future runtime environment or installation destination. The colocated
supervisor status file reported `worker_pid=1299257`, `state=serving`, updated
`2026-11-24T17:01:07.659471+00:00`, but contained no `runtime_identity` receipt.
Consequently it provides no target-bound host boot ID, process-start identity,
executing import root, installed digest, capability fingerprint, or reviewed /
integrated binding. A PID and serving state alone are explicitly insufficient.

## Required exercise manifest

The exercise owner must complete this manifest from independently inspected
evidence immediately before execution. Every SHA is a full commit ID and every
path is absolute.

| Field | Current preflight result | Owner and next supported action |
| --- | --- | --- |
| Product and tracking roots | Colocated candidate root identified above; dirty and therefore refused. | Repository operator selects the intended product/tracking roots, checks their configured roles, branch names, repository identities and clean status, and records both even when colocated. |
| Accepted review | Missing accepted review URL and exact source commit for the complete repair. | Review authority accepts the final review; operator prepares a clean detached or dedicated checkout at that exact commit. |
| Integrated target | Missing final guarded target commit and repository identity. | Integration authority lands the accepted source and records the clean target checkout, branch, repository identity and ancestry proof. |
| Runtime environment and destination | Missing dedicated environment, interpreter and installation destination. The contributor interpreter is not nominated. | Installation owner identifies the existing supported environment and installation procedure; any new software or dependency requires separate approval. |
| Artifact and receipt | Missing installed-source SHA-256, signed version-1 deployment receipt, receipt ID, manifest ID and prior-known-good receipt. | Authorized installation actor installs through the README procedure, issues the signed receipt, and retains both new and rollback artifact bindings. |
| Actor and credentials | Missing authorized actor identity, installation approval, credential scope, protected HMAC key path, and forge scope. | Approval owner names the actor and least-privilege scopes; credential owner provisions the receipt key and any read/compare or publication credential without storing secrets in the repository. |
| Loaded process | Only the unbound PID/status observation above exists. | Operator starts with the authenticated manifest; launcher and host verifier record PID, boot ID, process-start identity, executable, import root, module origins/digests, capability fingerprint and observation time. |
| Original incident and budget | Missing the exercise's exact original incident ID, authoritative generation, bound Task budget ID, policy version and operation receipt IDs. | Watchdog/Task owner selects the retained incident and reads its existing `.cascade/executions.json` budget before injection. No restart or replacement action may mint another allowance. |
| Rollback | Missing prior-known-good artifact digest, signed receipt/manifest, compatible environment and verified rollback process observation. | Installation owner pre-authorizes the exact prior binding and tests only its read-only validation. Without it, the exercise must not begin. |

## Supported execution and injection boundaries

The normal operator route is the README contract: one Ctrl-C requests the
worker's bounded `drain_and_shutdown`; the separately authorized installer uses
the existing installation procedure; `cascade runtime-bootstrap` creates an
authenticated evidence manifest; `cascade up --root <product-trunk> --runtime-authority <manifest> --runtime-authority-key <key>`
starts supervision;
`GET /api/health` exposes the launcher-verified receipt; and
`reconcile_parent_lifecycle_incident` performs the fresh independent closeout.
Ordinary startup without authority may remain useful locally but is not exercise
proof. No direct private-function call, operator-trunk edit, site-packages
hotpatch, or lifecycle-file write is supported.

The owned broken-adapter injection point is the
`feature.feature_repair` capability descriptor in
`cascade.watchdog.capabilities.default_capability_registry`, whose executor is
`cascade.feature.recovery.recover_task` and whose adapter call boundary is
`cascade.feature.repair.feature_repair`. A controlled harness may make that
descriptor/adapter unavailable for the selected incident, then must observe the
typed probe prerequisite and use the external drain/install/restart bootstrap.
This preflight did not alter that descriptor or callable.

The owned lost-receipt injection point is in
`cascade.review.ensure_feature_review` after the exact Feature source ref has
been pushed and before the review-registry projection is durably recorded. The
authoritative comparison is the forge's source/target review snapshot plus the
fetched `refs/remotes/origin/<feature branch>` tip, compared with the validated
publication history and expected source/target heads. Replay may reuse an exact
remote effect; a changed target, divergent source, unavailable forge evidence or
unintegrated follow-up remains pending and must not cause a second publication.
No push or crash was injected by this preflight.

## Bounded rollback and preservation rule

On an admitted exercise failure, request the same bounded drain, install only
the pre-authorized prior-known-good artifact identified by its signed receipt
and digest, regenerate/revalidate its runtime-authority manifest if required,
restart through `cascade up`, and require a fresh host verification and health
postcheck. Do not delete or rewrite `.cascade/executions.json`, pending Task
merges, review records, worktree registrations, incident history, or queued
delivery. Those durable stores preserve the original incident, finite budget,
operation receipts and delivery obligation across both forward install and
rollback. If any prior binding, credential, clean checkout, drain route or fresh
postcheck is unavailable, stop with that prerequisite; do not attempt a partial
rollback.

## Task 003 architecture closure evidence

The Task 003 review boundary was the integrated Task 001/Task 002 implementation
through `f238169dfcb8a32768fb5d13c9314a8b1a49de72`, with the documentation change
tested at `ed8e49c4d8807b816988189ae69edb37fe54bee6`. It was reviewed against
`README.md`, `DESIGN.md`, `cascade/DESIGN.md`, and the Workspace, Feature, Task,
Watchdog and War Room designs. Workspace now owns explicit bodies and rationale
for `REQ-WORKSPACE-RUNTIME-001` and `DEC-WORKSPACE-RUNTIME-001`. The other
designs describe the implemented repair, immutable delivery, original budget,
remote-effect and fresh postcheck contracts; War Room remains a bounded health
consumer with no new authority or store. The reviewed set had no unresolved
local links, duplicate design-ID owners, or delivery history in design prose.

`cascade-landscape`, `cascade-context` and `cascade-containers` remain unchanged
because the implementation adds no person, external system, deployment or
persistent store. The signed receipt/key remain an external installation
authority, and launcher/worker remain one OS process tree.
`cascade-supervisor-components`, `cascade-cli-components`,
`cascade-team-components` and `cascade-war-room-components` remain unchanged
because runtime provenance belongs to the existing Workspace Commands component
and the Watchdog, team/publication and health-consumer interfaces retain their
owners. `cascade-workspace-commands-code` contains the five significant runtime
Functions under `element.component.workspace-commands`; the Task 003 model
correctly has no `loaded_runtime_identity` → `validate_runtime_authority` edge.
`cascade-watchdog-code` links `reconcile_parent_lifecycle_incident` to fresh
current-runtime verification. The requested Workspace, Feature, Task, Teams,
Dashboard and War Room Code views retain their existing nodes because no
significant declaration or ownership boundary changed there. Source validation
and the real renderer confirmed source paths, symbols, kinds, parents and
code-component bindings without changing an accepted snapshot.

The normal source trace is accepted clean source plus guarded integration and a
signed install receipt → bootstrap → launcher validation → safe-path worker
report → launcher process/byte/capability verification → health receipt → fresh
Watchdog postcheck. The failure/restart trace retains the original incident and
queued delivery when authority or process evidence is missing, dirty, stale or
mixed, then requires the bounded external bootstrap and a new process-local
observation. `reconcile_parent_lifecycle_incident` calls
`verify_current_loaded_runtime_identity` with the current supervisor receipt and
`default_capability_registry().fingerprint()`; startup evidence alone cannot
close the incident.

Two journey proofs remain outside this review conclusion. The Task 002 main
journey pushes and repeats reconciliation, but does not interrupt after the
remote push and before the local receipt is written. It also does not read and
assert the original incident budget across bootstrap and restart. Focused budget
tests establish the underlying budget contract, but do not compose that full
journey. Backlog Task 004, recorded at plan revision
`05b1296f6e3a4910347513d9b880a11bdce3a7b9`, owns those proofs and must reconcile
any later code, design or C4 change. Task 003 therefore verifies the architecture
against implemented behavior; it does not establish final Feature acceptance.

Verification commands and revision pins:

- `pytest -q tests/workspace/test_c4_source.py
  tests/workspace/test_runtime_identity.py
  tests/watchdog/test_parent_lifecycle_postcheck.py` passed 27 tests in 53.30s
  at `ed8e49c4d8807b816988189ae69edb37fe54bee6`. This covers the native Code
  metadata contract, independent runtime binding and fresh closeout refusal.
- `pytest -q
  tests/workspace/test_c4_render.py::test_real_pinned_renderer_publishes_one_validated_handoff_and_cache
  tests/war_room/test_architecture_browsing_browser_journey.py` passed 3 tests
  in 211.48s at the same commit. It exercised the real local renderer and
  Chromium Context → Containers → Components → Code, Level up, deep-link
  restoration and representative pinned-source retrieval.
- The render command above used architecture source blobs
  `model.dsl=824b5b1137046ea2b843e9f556e92bba61d3ccb0`,
  `views.dsl=2aff10f837a18ef1bb000eb40860c1e8c01a2ac8`, and
  `workspace.contract.json=5d99a7dee8a65a878b4049c0f2a3c15b4836e6ba`.
  Its 24-view closure digest was
  `bbace5a4e4470485c7e09d70925aed18245bd0a216f6193beea67bb90dbfa4a0`.
  It rendered cold in 51.381s (`cache_hit=false`) and reused the verified
  artifact in 0.066s (`cache_hit=true`). These are host measurements, not a
  universal latency promise. Enforced limits remain 180s, 100 views, 5,000
  target occurrences, 2 MiB generated source, 4 MiB per SVG and 16 MiB combined
  SVG.
- The read-only review covered 11 documentation files and found zero missing
  local link targets, 75 design IDs and zero duplicate owners. `git diff
  --check` passed on the Task 003 review tree. The three Git blob IDs above make
  the validated architecture inputs independently inspectable; no accepted
  snapshot was rewritten.

The Task/Feature lifecycle documents are tool-owned and reject direct SWE edits.
This artifact is therefore the closeout evidence for the parent to consume; the
repository guard refusal was not bypassed. No architecture gap remains in the
Task 003 review boundary. The operational gaps above are intentional external
prerequisites, and the Task 004 journey proofs remain open; neither is a claim
that the later exercise or final Feature acceptance completed.
