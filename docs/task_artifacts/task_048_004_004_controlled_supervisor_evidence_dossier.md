# Controlled supervisor recovery evidence dossier

## Outcome and admission decision

Deterministic recovery acceptance is green, but the controlled operational
exercise was not admitted. No authorized target manifest, signed installation
receipt and trust key, permitted fault, selected retained incident, or
prior-known-good rollback binding was supplied. The observed operator checkout
was also dirty and diverged from its remote. Local dependency readiness and a
running worker provide none of that authority. Consequently this Task performed
no installation, drain, restart, credential use, fault injection, provider
dispatch, publication, remote mutation, rollback, or lifecycle closeout.

Operational acceptance for `feat_048_004` and `epic_048` remains open. The
accountable owners are the CascadeCode deployment approval authority, runtime
installation owner, repository operator, and Watchdog/Task incident owner. Their
next supported action is to jointly provide and independently verify the
complete admission manifest below in a clean dedicated target checkout. Only
then may an operator run one permitted incident through the documented War Room
UI/agent route and bounded drain/install/bootstrap/restart path.

## Deterministic correction and gate evidence

The corrected F1 source is
`51cffe146b8b423027266f8469678c482e321c79`. A read-only `gh pr view 251`
observation on 2026-11-25 UTC reported PR
`https://github.com/vincentc-b/CascadeCode/pull/251` merged into
`epic/epic_048` as `abfe2b2089343f6167e2e46e24c3c5e35991f4ca`; its
`review-recovery` check completed successfully. Commit
`111319e52bd202fdabca20bdb315fa3a5f9f2627` is the supported merge of that F1
correction into F4. The F4 integration baseline
`f258bca3a0beaee66d3eedd1483218245e838ea7` contains the F1 correction and F2
correction `b9c2129558beaffd235a6c28ab25693a5cd71813`; all are ancestors of this
Task tree.

The mandatory workflow still includes the complete
`tests/test_review_health.py`, including
`test_validation_and_publication_failures_remain_owned_and_retryable`; it was
not excluded or weakened. The original budget was not reset. The Task 3
closeout and Feature record preserve four distinct pre-correction red runs, each
with the same mandatory assertion (`completed` expected,
`awaiting_owner_decision` observed): `e9ea4848` at 210.23 seconds,
`373cbb17` at 210.19 seconds, `10b9dd73` at 203.12 seconds, and `ab5de092` at
212.73 seconds. They remain open historical evidence and were not reclassified
or collapsed into one observation.

After correction, four focused material/provider regressions passed in 7.41
seconds. An earlier complete post-integration selection passed 163 tests in
231.25 seconds on `cf3ea5594d6d8381ce80441067bfc04427000723`. The accepted
Task 3 supervised `final_validation` is the later clean deliverable
`c2e8b60895beb0d304c51c382be13fe00c0b4d5c`: exit 0, 163 passed, two
existing Python multi-threaded `fork()` deprecation warnings, 165.69 seconds.
The Task 4 supervised delivery receipt identifies the exact clean dossier commit
and is authoritative for this Task tree; no later edit may reuse that receipt.

The changed-material proof uses the production validator and Git path. It
retains the original incident across restart, refuses unchanged, cosmetic and
A→B→A material, admits genuinely changed review material only against remaining
original allowance, preserves linked provider-parent receipt attributes, and
requires an independently authenticated finite extension after numerical
exhaustion. The approved finite defaults remain six tool attempts, six paid
turns, 1,800 process seconds, 1,800 model seconds, 3,600 elapsed seconds, and
200,000 known tokens. These are policy limits and fixture evidence, not claimed
usage for the unexecuted operational exercise.

## Fresh-workspace reproduction

Repository and remote identity for the deterministic checkout are
`vincentc-b/CascadeCode` and
`https://github.com/vincentc-b/CascadeCode.git`. From a fresh checkout of the
tested revision, the exact supported setup and bounded command are:

```bash
git clone https://github.com/vincentc-b/CascadeCode.git
cd CascadeCode
git checkout c2e8b60895beb0d304c51c382be13fe00c0b4d5c
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
timeout --kill-after=10s 8m \
  python -m pytest -q \
    tests/test_late_repair_convergence.py \
    tests/task/test_incident_budget.py \
    tests/agent/test_provider_recovery_contract.py \
    tests/test_review_publication_safeguards.py \
    tests/test_review_recovery_journey.py \
    tests/test_review_health.py \
    tests/test_review_rebase.py \
    tests/test_resolution_actions.py \
    tests/watchdog/test_reservations.py \
    tests/watchdog/test_audit_investigation.py \
    tests/watchdog/test_parent_lifecycle_postcheck.py \
    tests/feature/test_publication.py::test_review_recovers_remote_creation_before_local_registry_write \
    --tb=short
```

Exit 124 is a failed gate. The automatic `.github/workflows/recovery-contract.yml`
job runs on pull requests and pushes to `main`, has a ten-minute job bound, uses
an eight-minute pytest bound, removes its raw log, and on failure retains only a
redacted tail of at most 64 KiB for seven days.

## Read-only operational observation

The candidate product and tracking root observed on 2026-11-25 UTC was the
colocated `/home/ubuntu/dev/CascadeCode` repository, branch `main`, repository
remote `https://github.com/vincentc-b/CascadeCode.git`, at
`c2ade1e50726c81148dc4fa9d3142ac73f7e9079`. It was not selected or admitted:
the branch was ten commits ahead and four behind `origin/main`, and
`architecture/review-units.json` was modified. This Task worktree is validation
evidence only; it is not an installation source or operator trunk.

The local supervisor status reported worker PID `1299257`, process start
`2026-11-24 17:01:04 UTC`, state `serving`, and status update
`2026-11-24T17:01:07.659471+00:00`. Its `runtime_identity` was null. It therefore
provided no authenticated product/tracking binding, boot identity, process-start
identity, installed digest, signed receipt, reviewed/integrated binding, import
root, module digest, capability fingerprint, or loaded-worker capability
generation. A PID and serving state are not deployment evidence.

Because operational admission was refused, the following evidence is honestly
`unavailable`, not zero or inferred from deterministic fixtures:

| Required operational field | Observation |
| --- | --- |
| Selected original incident, action and material generation | `unavailable` |
| Actor identity, credential scope and resolved capability | `unavailable` |
| Validation profile, policy owner and approval revision | `unavailable` |
| Original budget ID and cumulative operational usage | `unavailable` |
| Actual model/token usage | `unavailable` |
| Claim, reservation, operation and decision IDs | `unavailable` |
| Injection, interruption and restart points | `unavailable` |
| Tested and published operational SHA | `unavailable` |
| Accepted operational review and integrated deployment revision | `unavailable` |
| Signed artifact digest, receipt/manifest IDs and trust-key identity | `unavailable` |
| Loaded-worker boot/process/capability generation | `unavailable` |
| Independent remote and deployment observation | `unavailable` |
| Fresh original-obligation postcheck generation and result | `unavailable` |

No paid work or publication occurred, so this Task does not claim an operational
exactly-once result. The deterministic journey separately proves one physical
provider dispatch, red/green immutable Task validations, two worker PIDs across
restart, one review creation, one review-opened message, expected bare-remote
updates, and one terminal resolved receipt in both colocated and split-root
fixtures. Denied approval, credential, capability, dirty-source, stale-policy,
remote-drift and unavailable-evidence gates remain closed before an unpermitted
effect. Verified review delivery remains distinct from product acceptance and
from unresolved Feature/Epic operational obligations.

## Admission manifest still required

The named owners must supply all of the following together; a partial manifest
does not authorize the exercise:

1. The repository operator identifies clean absolute product and tracking roots,
   their configured roles, branches, repository identities and exact accepted
   and integrated revisions.
2. The review/integration authority identifies the accepted review and clean
   guarded target commit, with ancestry proof.
3. The installation owner identifies the supported environment and destination,
   authorized actor, least-privilege credential scope, signed version-1 receipt,
   artifact digest, receipt/manifest IDs and protected trust-key path.
4. The Watchdog/Task incident owner selects one retained original incident and
   reads its existing policy, generation, claim and cumulative budget before any
   injection. Restart or a replacement action must not mint allowance.
5. The approval authority names one bounded permitted fault and cleanup, and the
   installation owner pre-authorizes a signed prior-known-good artifact plus the
   bounded drain/rollback/restart route.
6. Immediately before injection, the operator independently verifies the loaded
   PID, host boot and process-start identity, executable, import root, module
   origins/digests, capability fingerprint and current signed receipt.

The supported route is War Room UI/agent admission followed, when required, by
one Ctrl-C bounded drain, authorized installation, `cascade runtime-bootstrap`,
and `cascade up --root <product-trunk> --runtime-authority <manifest>
--runtime-authority-key <key>`. Completion requires independent forge/remote and
loaded-process observations plus
`reconcile_parent_lifecycle_incident` rechecking the original obligation. Direct
private-function calls, lifecycle-file edits, hotpatching, raw success setters,
or bypassing review/credential/installation gates are not permitted.

## Final design and diagram-impact review

Reviewed `DESIGN.md`, `cascade/DESIGN.md`, and
`cascade/{task,agent,watchdog,workspace,epic,feature,war_room}/DESIGN.md` against
the complete integrated diff after F3 Tasks 003/004 and F4 Tasks 001–003. Also
reviewed the revision-pinned `model.dsl`, `views.dsl`, and
`workspace.contract.json` source contract. No accepted snapshot was rewritten.

| Level / views | Final result and precise no-change reason |
| --- | --- |
| `cascade-landscape`, `cascade-context` | No person, provider, forge, operator responsibility or external dependency changed. This dossier records a refused operational admission. |
| `cascade-containers` | No deployed process, communication path, persistent store or isolation boundary changed. CI diagnostics and test repositories are ephemeral. |
| Supervisor, team, CLI and War Room component views | Existing admission, scoped owner, publication, runtime bootstrap, health consumer and independent postcheck responsibilities remain unchanged. No route or component owner changed. |
| `cascade-task-code` | The integrated `reserve_incident_operation` / `settle_incident_operation` material-fingerprint and original-allowance behavior remains owned by Task. Paths, Function kinds and owner are current. |
| `cascade-agent-code` | Provider admission, settlement and physical-dispatch wiring are unchanged; this Task launched no provider work. |
| `cascade-watchdog-code` | Reservation, capability resolution, investigation deduplication and `reconcile_parent_lifecycle_incident` ownership remain current. |
| `cascade-teams-code` | `publish_team_review_resolution` supplies immutable source material to the existing validation/publication pipeline. Source path, Function kind and Teams owner remain current. |
| Epic, Feature, Workspace, Workspace Commands, Dashboard and War Room HTTP Code views | No symbol, declaration kind, owner, library/tool wiring, HTTP/CLI route, persistence contract or renderer behavior changed. |

The final normal trace remains original incident admission → scoped owner →
immutable validation → lease publication → independent remote and loaded-runtime
observation → fresh Watchdog postcheck. The failure/restart trace retains the
original incident, cumulative budget and exact receipts at the first refusal;
dirty source, missing authority, stale evidence or unavailable runtime identity
cannot close it. Worktrees, local locks and process groups remain correctness
boundaries, not OS, network or credential isolation.

Task 3's final integrated checks covered real symbols, declaration kinds,
parents and Code-view owners; Context → Container → Component → Code, Level up,
deep-link restoration and pinned-source opening; stale-symbol rejection; normal
and failure states; bounded scheduling; and warm artifact reuse. The 18-test
source/navigation selection passed in 4.82 seconds. The unmodified pinned
renderer plus Chromium journey passed three tests in 190.48 seconds (196.77
seconds wall, 175,260 KiB maximum RSS). `docker image inspect` bound that
measurement to repository-pinned image
`structurizr/structurizr@sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`;
its distinct local Docker image ID was
`sha256:97681b22557abb2044ff2b67ae374956824c01da46b76be60858281adf678864`.
It exercised failure states and verified warm reuse without a per-view renderer
launch.

Task 4 then reran the recovery and source/navigation selection on clean Task
tree `f26f5af7f918d0c5bcf56237784d0a9d765632ff` (181 passed in 195.82
seconds), the pinned renderer case (one passed in 47.46 seconds), and the
Chromium architecture journey (two passed in 132.66 seconds). The subsequent
correction changes only this evidence prose: `model.dsl`, `views.dsl`,
`workspace.contract.json`, production source, designs, view keys and browser
code are byte-unchanged. The final supervised Task validation therefore reruns
the scoped recovery/source contract on the exact clean corrected dossier commit;
the renderer and browser observations are inherited from `f26f5af7` for this
prose-only delta rather than presented as a new render.

## Remaining acceptance obligations

The deterministic CI/review correction is verified; the operational exercise is
not. The F1 owning team must also publish the still-missing reconciliation
receipt that binds its accepted correction, PR #251 review-recovery result and
downstream integration; ancestry and the F4 gate do not substitute for that
owner receipt. The Feature and Epic must not be recommended complete until that
receipt exists and the accountable operational owners provide the manifest, one
permitted incident is exercised through the supported route, actual or
unavailable usage is recorded from that run, exact
incident/claim/reservation/decision identities are retained, publication is
independently observed without duplication, the loaded signed source is
verified, and a fresh postcheck resolves the original obligation. This dossier
is bounded to non-secret identifiers and sanitized observations and contains no
credential, trust-key material, raw provider output or unbounded diagnostic log.
