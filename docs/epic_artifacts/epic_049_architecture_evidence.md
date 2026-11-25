# Epic 049 architecture planning review

## Reviewed decision and scope

The canonical Epic spec owns the proposed progress, source-receipt, liveness,
transcript append/replay and bounded history contract (dec_004–dec_007). All three
backlog Feature specs were read and updated through Cascade; their required Task
acceptance now includes that contract. Runtime progress/milestones are not
implemented by this planning pass. No child was dispatched, dependency installed,
external message sent, or accepted architecture snapshot rewritten.

Current implementation coverage is committed in the owned integration branch.
`model.dsl`, `views.dsl` and `workspace.contract.json` contain 13 additional real
Function nodes, nine code relationships, component design links and current
Dashboard responsibility wording. Source ownership is bound to this proposal.
Model inventory: 209 elements, 241 relationships, 24 views.

A concrete UI blocker was fixed during review: default full-model snapshot
metadata measured 271,703 bytes against the existing 262,144-byte cap. A one-view
page measured 247,548 bytes. Offline diagnostic sizing captured these values;
no oversized response was served and no production cap was raised. The HTTP
route now reduces the view page, preserves all targets and emits advancing
continuation. The document-context consumer follows continuation as well.
Metadata plus one view that cannot fit still returns HTTP 413. This is the only
product behavior changed during planning.

## Design and diagram impact reconciliation

| Level / views | Review and result |
|---|---|
| `cascade-landscape`, `cascade-context` | Root context remains accurate: same operator, local system, repository, provider and forge. No topology change. |
| `cascade-containers` | Root and package runtime/storage boundaries remain accurate; transcript helpers are in-process library code, not a new deployed service. |
| `cascade-supervisor-components`, `cascade-team-components`, `cascade-war-room-components` | Preserved component ownership; clarified Dashboard responsibilities and added direct links to War Room, Task, Watchdog and Workspace designs. |
| `cascade-dashboard-code` | Added routing-based recovery summary, selection, chat GET/read/append, post-turn mirror and explicit backfill functions. War Room design documents their actual coarse-state/full-read/thread-only-lock limits. |
| `cascade-task-code` | Added owner acknowledgement, attempt claim, checkpoint and finalization functions; Task design shows locked state, external execution and interrupted-claim recovery. |
| `cascade-workspace-code` | Added graph invocation and process-local owner observation. Workspace design distinguishes queued ownership from executing attempts and links the transcript handoff sequence. |
| `cascade-watchdog-code`, `cascade-teams-code` | Existing receipt, exact-generation postcheck and publication nodes still describe current code. No new producer is implemented here. Feature tasks own the proposed notification/drain/liveness updates. |
| `cascade-architecture-browser-code` | Existing `snapshot_projection` node and browser/API relationship cover the bounded page-sizing correction. Its internal helper and document-context continuation remain within that responsibility; no additional component, Code view or render process is introduced. |
| Behavioral diagrams | War Room adds graph-return and interruption/backfill sequence; Task adds attempt/claim lifecycle. Workspace and package link to these owners rather than duplicate them. Proposed crash matrix and live progress sequence remain in the Epic spec. |

Reviewed changed designs: `cascade/DESIGN.md`, `cascade/war_room/DESIGN.md`,
`cascade/task/DESIGN.md`, `cascade/workspace/DESIGN.md`. Reviewed affected root
context/audit/container sections and Watchdog producer/postcheck interfaces.
Removed stale War Room baseline inventory and historical phrasing. Added stable
local transcript, action-evidence and turn-evidence requirement/decision IDs in
exactly one owning design each. All local file links and heading anchors in the
four changed designs resolve; 13 added Function declaration kinds and symbols
were checked using Python AST against their real source files. No new directory
boundary was created. Source contract validation passed.

## Inspectable checks

- `python -m pytest -q tests/workspace/test_c4_source.py tests/war_room/test_recovery_incident_projection.py tests/war_room/test_planning_transcript.py tests/war_room/test_chat_poll_routing.py tests/war_room/test_projection_batching.py`: **29 passed in 2.86s**.
- Final `python -m pytest -q tests/war_room/test_architecture_http.py --tb=short`: **13 passed in 15.66s**. The expanded HTTP scenario verifies smaller pages, every view exactly once, preserved targets, advancing cursors, later-page document context and minimum-page refusal. Existing cases verify forged resources and selections, missing/stale references, and pinned source surviving replacement/deletion of the original function in the newer checkout.
- C4 metadata tests reject invalid component ownership and escaping source paths. No existing symbol was renamed or removed by this diff; new symbols and their single Code owners were resolved against source.
- The pinned Docker/Structurizr renderer produced all **24 interactive views**. The model/source revision used in the final browser journey is `01e1cff36a48b8abe3771708936921a93bc83643`. Runtime route code at that commit includes both pagination fixes. A subsequent test-only commit corrects the artificial fixture's selected-context byte allowance; later planning prose does not change the tested route or modeled functions.
- The default renderer retains its **180-second** deadline and existing memory/CPU/PID bounds. A cold render at `dfcc7f9c79926c2bddd673d1f8599482a3670680` took **45.47s**; reproducing the final pinned artifact from cache took **0.54s**. These are local observations, not latency promises.
- [Reproducible Chromium smoke](epic_049_architecture_browser.py) and [captured results](epic_049_architecture_browser.json): real production architecture routes, real rendered SVGs, and default request paging. Unrelated operational-panel requests are stubbed to avoid inspecting other teams; no architecture endpoint or result is mocked. All three paths traverse context → container → component → Code, restore a target deep link, open pinned source and Level up. Covered `append_planning_turn_to_chat`, `_claim_resume_attempt`, and `graph_turn_owner_is_live`. **No architecture HTTP errors** were observed. Initial cold browser readiness was **66.16s**; paths including reload/source/context requests took **8.92s**, **8.33s**, and **12.46s**. Render-operation count stayed **3 → 3** across navigation. Reload/close can cancel in-flight HTTP responses and produce server BrokenPipe diagnostics; there were no failed completed architecture responses.
- `git diff --check` passed. No full repository suite was claimed or required.

## Normal and interruption traces

Normal current path: a routed owner enters supervision and
`acknowledge_team_recovery` commits its matching acknowledgement;
`resume_action` claims an attempt under the lifecycle lock, releases the critical
section before the executor, and finalizes its result. Independent Watchdog
postcheck, not publication or attempt success, proves resolution. After the graph
returns, `_invoke_role_turn` forwards the new saved messages to the transcript
writer. Existing board projection may still call queued work investigating;
the proposed producer is required to replace that coarse display semantics.

Failure/current restart: a crash can leave a durable open attempt and checkpoint,
while process-local queues/locks disappear. Review-publication reconciliation
uses exact process identity; unknown ownership is not death. A checkpoint-to-chat
gap is repaired only by explicit sync, whose author/body deduplication and
thread-only locking have documented limits. These facts justify the proposed
source receipts, graph fence, pending append intent and stable message identity.
No test in this planning review claims the proposed crash matrix already passes.

## Limits and handoff

The proposed live progress, two-process transcript protocol, legacy import,
room movement and operational recovery timeline remain Feature implementation
acceptance, with exact Task obligations in the Epic and child specs. Large target
metadata that cannot fit even one view still fails explicitly; this correction
does not introduce target pagination or claim arbitrary model scalability.
Related epics' scoped historical records and accepted review ancestry were not
established; current local code and the supplied timeline are the evidence basis.
No production deployment or provider/forge recovery was exercised.

The exact publication request is retained in
[epic_049_architecture_review.json](epic_049_architecture_review.json).
An empty accepted lineage for `epic:epic_049` was read from the canonical store;
publication therefore uses generation `null`. Publication status and architect
sign-off are authoritative in Cascade. If publication returns pending, replay
that identical request on a later turn; do not substitute newer unreviewed pins.
The Epic Manager must review and sign off on the final plan revision separately.

## Epic Manager final planning review

Reviewed plan `032809336f3fcf3810c7270c28195da9c85a3bf6` and read all three
backlog Feature specs through Cascade. The three sequential slices cover the
eight success criteria without adding repair authority, a scheduler or paid
commentary turns. Feature scope carries the selected receipt, liveness, replay,
read-budget and diagram obligations into required Task acceptance. Concrete
Feature APIs and Tasks remain normal child planning work, not completed work.

Reviewed the four changed designs listed above against the final diff, the root
context/audit contract and the Watchdog verification boundary. Current-code
claims agree with `resume_action`, `graph_turn_owner_is_live` and
`_invoke_role_turn`: claim/preflight is locked, execution occurs outside that
critical section, queued owner evidence is not execution proof, and current
authored transcript mirroring follows graph return. An interrupted attempt and
the checkpoint-to-chat gap remain distinct recovery cases. No further design
edit is needed: proposed progress and append protocols stay in work records.
The level-by-level inventory above and the Epic inventory assign implementation
updates and verification to the three Feature teams, including integrated Code
views and normal/failure/restart scenarios.

Independent checks on the reviewed checkout:

- `python -m pytest -q tests/workspace/test_c4_source.py tests/war_room/test_architecture_http.py`:
  **27 passed in 9.94s**.
- `validate_c4_workspace` returned `C4WorkspaceContract`.
- All five saved design/model/contract references match their committed SHA-256
  digests and current checkout bytes; no reviewed pin was replaced.
- Inspected the saved Chromium journey and results: three context-to-Code,
  pinned-source, deep-link and Level-up paths passed, with render-operation
  count unchanged. This review did not repeat the browser run or claim new
  product acceptance.
- Read-only epic comment enumeration returned no threads; Cascade returned no
  architecture amendments. All three Features remain in backlog with the
  declared dependency order.

Manager review is complete; role sign-off is recorded separately by Cascade.
Architecture publication remains pending and must be resumed by the Epic
Architect with the identical saved request. `cascade/agent/mcp_wrappers.py`
explicitly withholds `publish_architecture_review` from Epic Manager sessions;
this review did not bypass that role boundary. The runtime implementation,
crash matrix, operational recovery fixture and scoped historical-provenance
limits above remain open delivery obligations, not plan-review failures.

## Architect publication replay outcome

Replayed the identical saved request after canonical `read_doc` confirmed plan
revision `032809336f3fcf3810c7270c28195da9c85a3bf6`. Cascade returned **failed**,
reason `internal_error`: "render worker was interrupted after its automatic
recovery attempt". No review unit or amendment was created by this operation.

- Publication operation: `architecture-publication-9b870c091d516f233c9a27d0b7d088f4770c7fe0c753343719515962f238776e`.
- Render operation: `c4-render-e33148f7d2456ca7b316d71b615a7588cfb5e2fd884a335fcdff3bb5e44c5a5e`.
- Reviewed tuple: `708549cdf023f9f691aa4b2632671c3bb09b8e29a83f0b30ceef64ba4778c51f`.

This result supersedes the pending status recorded above. The saved request,
generation, plan, design and model pins remain unchanged. Verified all five
design/model/contract references against both committed SHA-256 digests and
checkout bytes; reviewed the four changed designs and their affected interfaces
against the planning diff and the existing level-by-level inventory. No further
design change is needed for an interrupted render worker. `git diff --check`
passed. Existing test/browser evidence above remains applicable; no new test or
browser run is claimed for this replay.

Runtime recovery handoff: inspect the publication and render operations above
and provide a supported retry that preserves their failure history and exact
reviewed tuple. `discover_architecture_publication` returns terminal publication
rows without scheduling work, so repeating this failed request cannot restart
the renderer. The Architect's available Cascade tools expose publication but no
failed-publication retry. No direct ledger edit, accepted-snapshot rewrite,
replacement proposal or runtime restart was attempted. Both plan sign-offs remain
on the same revision; architecture publication is still incomplete.

## Epic Manager feature-planning handoff

Reviewed the `FeaturePlanningStarted` event for `feat_049_001` against canonical
Epic revision `032809336f3fcf3810c7270c28195da9c85a3bf6`, Feature 1 draft
`5de5f2d41d3af751dac47a9dd43639fe010be942`, and both dependent Feature specs.
Cascade returned no architecture amendments. Feature 1 is active; Feature 2
depends on Feature 1, and Feature 3 depends on both. The existing Epic contract
and role sign-offs remain unchanged; this handoff adds no requirement or decision.

The Feature 1 draft now assigns source receipts, invocation/executor observations,
materialization and read APIs to four task slices. Its acceptance carries the
approved identity, after-lock notification, pre-executor publication, bounded
supervisor replay, 30-second liveness ceiling and aggregate read budgets.
Preserve these boundaries when minting Tasks. Deliver the frozen receipt/entry
identity and API contract as shared artifacts for Feature 2's subsequent planning;
pending milestone references remain explicit until that consumer commits them.
Feature 2 owns append/deduplication and bounded history; Feature 3 owns the held
final-reply operational journey and coherent UI. Feature 1 delivery must not
claim either downstream acceptance has already passed.

Reviewed the Task action-evidence, Workspace invocation and War Room transcript
design sections and their parent/Watchdog interface references. No design or
model change is needed for this planning event: source behavior and architecture
boundaries are unchanged. The existing level-by-level inventory remains assigned
to the Feature teams; Feature 1's task breakdown explicitly includes actual
source symbols, native Code views, normal/dead-owner/restart cases and navigation
verification. Its implementers must reconcile these against their final diff.

The terminal architecture-publication failure above remains open with the
runtime recovery owner and Epic Architect. Feature work proceeds under the
approved plan, but the publication gap must remain visible in delivery evidence;
local rendering and signed planning are not successful publication. No retry,
replacement publication or accepted-artifact change was attempted here.

Verification for this handoff is canonical spec/dependency-order review and
`git diff --check`; no executable code changed and no test run is claimed.

## Architect feature-planning handoff review

Read the canonical Epic and Feature 1 revision
`5afb0c3577efec331dcac74de9b9b1c2ae4c3564` through Cascade. Feature 1 now lists
four Task records and assigns receipt durability, exact invocation/executor
evidence, materialization and bounded public reads to them. Its diagram inventory
assigns all affected levels, native Code nodes, normal/dead-owner/restart flows,
pinned source opening and warm navigation verification. This review verifies
the Feature contract and assignments, not individual Task content or execution.
The approved Epic revision and both existing sign-offs remain unchanged;
Cascade returned no architecture amendments.

Reviewed the War Room transcript, Task action-evidence, Workspace invocation,
package recovery and Watchdog postcheck interfaces against the existing design
inventory. No model or design edit is warranted: the only intervening owned
diff is the Manager's handoff evidence, with no changed runtime behavior or
boundary at context, container, component, Code or behavioral levels. Proposed
implementation and its verification remain assigned to Feature 1; transcript
deduplication/history and the held-final-reply UI journey remain downstream.
Preserve the frozen receipt/entry identities and explicit pending milestone
references at that handoff.

Verified all five saved design/model/contract references against committed
digests and checkout bytes; `validate_c4_workspace` returned
`C4WorkspaceContract`. `git diff --check` passed. No new executable tests or
browser journey were run for this documentation-only review.

The available Cascade tools still expose no retry for terminal architecture
publication failure. Source inspection confirms that discovery returns a failed
row without scheduling; the special retry branch applies only to
`superseded/artifact_changed`, not this `failed/internal_error` outcome. Do not
change reviewed pins to manufacture a new operation. The exact request and
operation IDs above remain the runtime recovery handoff. Publication is still
incomplete; this turn does not claim a retry or a new publication result.

## Progress v1 consumer contract routing

Handled TeamMessage `feat_049_001:feat_049_001_contract_handoff_20261125`.
Read the canonical Epic and both Feature specs through Cascade. Feature 1
revision `9c97b16f8c3d6853c7a1903cbaddd71c1fcd83e0` owns the proposed receipt,
entry and bounded progress API contract. Feature 2 remains backlog, dependent
on Feature 1. Saved the producer handoff into Feature 2's Data structures,
API contracts and Risks sections through `write_doc`, then read back revision
`f93d076a2ae29233bff668aa4f76ad320315c1c2`. Existing scope, lifecycle metadata,
model selections, dependency order and transcript acceptance are preserved.

Cascade enqueued `epic_049:progress_v1_consumer_confirmation_20261125` to
Feature 2 and `epic_049:progress_v1_handoff_routed_20261125` to Feature 1.
Consumer agreement is pending, not implied by this parent review. Feature 2
must return agreement or exact identity/field/route/error/cursor/sanitization
mismatches through the parent. Feature 1 Task 4 supplies fixture paths and
revisions, including canonical identity serialization, absent-value treatment,
nested payloads/error discriminators and receipt-to-milestone linkage. Ordered
milestone references remain pending until the transcript event is durable.
The separate transcript API remains Feature 2's responsibility.

Reviewed the War Room recovery/transcript, Task action-evidence and Workspace
invocation/transcript design sections and their parent/Watchdog references.
No design/model edit is warranted for this routing-only change: context actors
and container boundaries are unchanged; component ownership and current Code
symbols are unchanged; no implemented execution, persistence or recovery flow
changed. The existing diagram-impact inventory and Task verification ownership
remain in force. Proposed interface detail stays in work records until source
implementation. The Epic revision/sign-offs are unchanged. Architecture
publication remains an unresolved runtime-recovery handoff, as recorded above.

Verification: canonical Feature 2 readback confirmed the saved handoff and
preserved metadata; both message calls returned `enqueued`; `git diff --check`
passed. No executable code changed, and no new test or browser run is claimed.
Return control for child work; relay the consumer response on its next event.

## Architect consumer-handoff review

Compared the canonical producer revision `9c97b16f8c3d6853c7a1903cbaddd71c1fcd83e0`
with consumer revision `f93d076a2ae29233bff668aa4f76ad320315c1c2`.
The routed receipt/entry identities, safe fields, progress route, revision-bound
cursor and pending milestone linkage agree. Exact serialization, nested payloads
and error discriminators still require Task 4 fixtures and explicit consumer
confirmation; this review does not supply that confirmation. The consumer's
separate transcript interface remains its own planning obligation.

Reviewed War Room recovery/transcript, Task action-evidence and Workspace
invocation sections with package/Watchdog interface references against the
routing-only diff. The existing level-by-level inventory remains applicable:
no context actor, container boundary, component owner, implementation symbol or
execution/restart flow changed. No design/model update or repeated runtime test
is warranted. Canonical amendment lookup returned none; `git diff --check`
passed. Epic revision `032809336f3fcf3810c7270c28195da9c85a3bf6` is unchanged.
Available tools still expose no terminal-publication retry; the recorded failed
operation and exact saved request remain the runtime recovery handoff. Return
control for child execution and the pending consumer response.
