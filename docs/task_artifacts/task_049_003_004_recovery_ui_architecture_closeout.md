# Recovery UI architecture and integrated closeout

## Pinned integrated boundary

This reconciliation runs on the integrated Task 3 baseline and pins the
producer ancestry to Feature 4 handoff
`a3d4a42b3df92a553206c300c42142600183eaef`. Git ancestry checks also confirm
patch-equivalent atomic mapping commit `2e9fe23e` and UTF-8 detail commit
`ecd390f4d1819d72bc65e2ea4960000a48e50a67` as ancestors. The original atomic
mapping revision is `469f0fa5f0bd99cf38351e26d6d7feb952bb26d3`;
the Feature plan records stable patch ID
`e24afbbe865d97c4e36541295f22815edd6af942` for that equivalence.

The integrated source delta after the pinned Feature plan changes only two
recovery behaviors. `recovery_progress.publisher._has_timestamped_acknowledgement`
recognizes the production `owner_acknowledged` receipt and nested routing time.
`task.action_recovery.resume_action` registers its exact executor observation
before notifying the committed execution start. The latter ordering is already
reconciled in `cascade/task/DESIGN.md`. Neither change adds a runtime, store,
external dependency, component, source declaration, or ownership boundary.

## Design ownership review

The final diff was reviewed against `DESIGN.md`, `cascade/DESIGN.md`,
`cascade/war_room/DESIGN.md`, `cascade/task/DESIGN.md`,
`cascade/watchdog/DESIGN.md`, `cascade/workspace/DESIGN.md`, and
`cascade/recovery_progress/DESIGN.md`.

- `cascade/recovery_progress/DESIGN.md` is the sole producer owner of
  `REQ-RECOVERY-PROGRESS-001` through `004` and
  `DEC-RECOVERY-PROGRESS-001` through `002`. The identifiers occur only in
  that design; its verification table refers back to the same owned IDs.
- `cascade/war_room/DESIGN.md` owns the immutable GET, browser consumer,
  Historical paging/detail, transcript writer/index and room-incarnation
  contracts. Its progress requirements are presentation requirements, not a
  second copy of producer authority.
- `cascade/task/DESIGN.md` owns durable action attempts, transition receipts,
  exact executor identity and the start-before-reply sequence.
- `cascade/workspace/DESIGN.md` owns queued/invoking graph identity,
  checkpointed authored replies and revision-pinned architecture rendering.
- `cascade/watchdog/DESIGN.md` delegates the progress producer/index protocol
  to Recovery Progress and documents Watchdog admission and replay callers.
- The root and Cascade designs retain system-wide boundaries and navigation;
  no current fact was duplicated or delivery chronology added to a design.

No additional design edit is justified by the final source diff. The current
Task sequence already states the changed token/notification ordering, while the
other reviewed documents accurately describe unchanged interfaces, state and
failure behavior.

## Diagram-impact inventory

The authoritative source is
`architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`.
All three files agree on the following views, native Code scope, semantic IDs,
source paths, source symbols and declaration kinds.

| Level / view | Owning design and representative source | Integrated result |
|---|---|---|
| Landscape / `cascade-landscape` | Root `DESIGN.md`; Operator, Cascade, Git forge, model provider and Structurizr systems | No change. The integrated diff introduces no person, system or external dependency. |
| Context / `cascade-context` | Root `DESIGN.md`; the same system responsibility boundary | No change. Recovery remains a Cascade responsibility and local immutable projections remain repository artifacts. |
| Containers / `cascade-containers` | Root and `cascade/DESIGN.md`; War Room, Service, Operator CLI and Repository artifacts | No change. Task ledgers, transcript JSONL/index and immutable pages remain in existing repository/runtime boundaries; no deployment or isolation boundary was added. |
| Components / `cascade-war-room-components` | `cascade/war_room/DESIGN.md`; `loadCurrentRecoveryProgress`, `pollChatSidecar`, `handle_get_transcript`, `read_transcript_page` | No relationship change. Existing Dashboard and HTTP components own the progress/transcript consumers exercised by the integrated journey. |
| Components / `cascade-supervisor-components` | Cascade, Task, Watchdog, Workspace and Recovery Progress designs; `resume_action`, `publish_committed_transition`, `drain_recovery_progress`, `begin_live_observation` | No component change. The changed acknowledgement recognition and notification ordering stay inside existing Task team/Watchdog responsibilities. |
| Components / `cascade-team-components` | `cascade/DESIGN.md` and `cascade/task/DESIGN.md`; `ensure_task_graph`, `run_swe_turn`, `resume_action` | No change. The held reply still runs through the existing Task team, Agent and Repository collaborators. |
| Code / `cascade-dashboard-code` | `cascade/war_room/DESIGN.md`; `loadCurrentRecoveryProgress`, `pollChatSidecar`, `board_recovery_projection`, `read_recovery_progress`, `_derive_entry`, `handle_get_transcript`, `read_transcript_page`, `read_transcript_detail`, `publish_transcript_projection` | No node change. Task 1/2 browser and page declarations remain real Functions. Task 3 changes acknowledgement classification below `_derive_entry`; the modeled safe-contract entry point and ownership remain accurate. |
| Code / `cascade-war-room-http-code` | `cascade/war_room/DESIGN.md`; `serve`, `WarRoomRequestHandler`, `HumanIdentityVerifier`, `LocalHumanIdentityVerifier` | No change. No route, authentication, handler or HTTP failure mapping changed. |
| Code / `cascade-task-code` | `cascade/task/DESIGN.md`; `resume_action`, `_record_execution_start`, `_executor_live_identity`, `_notify_transition`, `_append_action_transition` | Behavioral ordering changed: start commit → exact executor token → after-lock notification → executor. Existing Function nodes, relationships and owner remain correct; the supplementary Task flow records the ordering. |
| Code / `cascade-watchdog-code` | `cascade/watchdog/DESIGN.md` and `cascade/recovery_progress/DESIGN.md`; `publish_committed_transition`, `drain_recovery_progress`, `record_transcript_milestone`, `_record_transcript_milestone` | No node change. `publisher._has_timestamped_acknowledgement` is a small classifier under the existing progress-publication entry point, not a separate architectural responsibility. |
| Code / `cascade-workspace-code` | `cascade/workspace/DESIGN.md`; `_invoke_role_turn`, `graph_turn_owner_is_live`, `_run_kickoff`, `begin_live_observation`, `refresh_live_observation` | No change. Queued work remains distinct from a live invocation token; checkpoint and authored-reply handoff behavior is unchanged. |
| Code / `cascade-teams-code` | `cascade/DESIGN.md`; `ensure_epic_graph`, `ensure_feature_graph`, `ensure_task_graph`, `run_planning_role_turn`, `run_swe_turn`, `publish_team_review_resolution` | No change. No team graph, validation or review-publication declaration changed. |

The native render contains 24 views. Source validation and the real render
proved that every modeled component has a reachable scoped Code view, every Code
node is included once under its declared `cascade.codeComponent`, every
`cascade.parent` agrees, and each `cascade.sourcePath`, `cascade.sourceSymbol`
and Function/Method/Class/Dataclass/TypedDict/Interface kind matches the actual
declaration. No planning-only node was present to remove. Accepted architecture
snapshots and review-unit records were not modified.

## Source-linked normal and failure flows

The normal held-reply path is:

1. `resume_action` commits `_record_execution_start` and its durable Task action
   receipt, then registers `_executor_live_identity` through
   `begin_live_observation` before `_notify_transition` runs.
2. `publish_committed_transition` joins the receipt to the exact live token,
   derives an executing entry, and calls
   `append_committed_recovery_receipt` for one deterministic transcript line.
3. `record_transcript_milestone` / `_record_transcript_milestone` starts the
   publisher transaction before
   `fenced_transcript_source_acknowledgement`, commits current graph/message/
   incarnation/append-sequence routing while the graph fence is held, and then
   publishes immutable work pages.
4. `loadCurrentRecoveryProgress` and `pollChatSidecar` read only the immutable
   progress/transcript pointers, manifests and bounded pages. The executing
   attempt and committed `System · Recovery` anchor can therefore appear while
   the authored role reply remains held. When `_invoke_role_turn` returns, the
   checkpointed reply is appended under its stable source identity.

The canonical state is split deliberately: Task's action ledger owns attempts
and receipts; graph checkpoints own authored replies; transcript JSONL owns room
history; its writer-only SQLite index owns offsets, uniqueness, intents and room
incarnation; Recovery Progress's disposable SQLite index owns receipt projection
and milestone mapping; immutable manifests/pages plus atomic pointers are the
GET surface.

For pending/restart behavior, an unfinished transcript append/rewrite/move,
incomplete import or unsafe owner causes
`fenced_transcript_source_acknowledgement` to fail pending without repair.
The mapping remains absent or unchanged and the retained receipt stays eligible
for bounded `drain_recovery_progress` replay. A later replay reuses the receipt
source key, so JSONL and mapping deduplicate. Delayed acknowledgements cannot
restore stale routing because the current fenced source acknowledgement, not a
saved caller incarnation, supplies graph/incarnation/append sequence during the
publisher commit. Room movement journals a fixed target incarnation; stale page
or detail cursors return restart and browser consumers discard that affected
state rather than splice graphs or incarnations. Dead, expired, inaccessible or
mismatched executor/worker identity stays unknown or stale and cannot prove
execution.

## Validation evidence

- `git merge-base --is-ancestor <revision> HEAD` passed for
  `a3d4a42b3df92a553206c300c42142600183eaef`, `2e9fe23e`, and
  `ecd390f4d1819d72bc65e2ea4960000a48e50a67`.
- `python -m pytest -q tests/workspace/test_c4_source.py tests/workspace/test_c4_render.py::test_real_pinned_renderer_publishes_one_validated_handoff_and_cache tests/war_room/test_architecture_browsing_browser_journey.py::test_branch_architecture_is_pinned_navigable_and_refreshes_whole_snapshot`
  passed 16 tests in 173.45 seconds.
- Source-contract mutations rejected stale/renamed symbols, missing parents and
  component-ownership drift before rendering.
- The pinned local renderer returned `ready` for all views, verified all real
  declaration kinds and source symbols, and the immediate second submission was
  a cache hit on the identical artifact directory. That proves warm reuse rather
  than per-view process startup; the renderer keeps the configured total
  deadline and one bounded batch capture for all views.
- The Chromium journey in
  `test_branch_architecture_is_pinned_navigable_and_refreshes_whole_snapshot`
  uses a reduced four-view fixture with only Agent runtime Code. It verifies
  browser navigation mechanics, deep-link restoration, pinned source access,
  Level up, forged-resource rejection and missing/broken model states. It does
  not verify those paths through the integrated Dashboard, Task, Watchdog,
  Workspace or Teams Code views.
- A separate feature-level Chromium run cloned merged revision
  `3d0691e2d51dd5b5b27717a659143fce3778148d` and served its full,
  unmodified 24-view model. For each row below, the browser selected context,
  clicked Cascade to containers, clicked the named container to components,
  clicked the named component to its native Code view, selected the code node,
  reloaded its snapshot/view/target deep link, opened the pinned source until
  actual JS/Python declaration text loaded, and used Level up through
  components and containers back to context. All five paths passed:

  | Container | Component | Native Code view | Pinned source symbol |
  |---|---|---|---|
  | War Room | Dashboard | `cascade-dashboard-code` | `war_room.js:loadCurrentRecoveryProgress` |
  | Service | Task team | `cascade-task-code` | `action_recovery.py:_record_execution_start` |
  | Service | Watchdog | `cascade-watchdog-code` | `publisher.py:publish_committed_transition` |
  | Service | Workspace | `cascade-workspace-code` | `architecture.py:resolve_design_ownership` |
  | Service | Tier teams | `cascade-teams-code` | `graph.py:ensure_task_graph` |

  This proves integrated navigation and pinned-source loading for representative
  affected components. The earlier reduced fixture remains separate evidence for
  malformed resource IDs and unavailable models. The run used a local isolated
  clone and does not claim a deployed browser session or resolve Feature 5.
- Task 3's operational closeout separately records the held-final-reply HTTP/
  Chromium journey, direct versus restart replay, service restart, immutable
  identity, read budgets and warm board/transcript measurements. Those results
  are behavior evidence, not a substitute for the architecture checks above.
- Final supervised clean-tree validation is recorded by the Task delivery gate
  after the deliverable commit.

## Explicit remaining gates

Feature 5's producer contention repair is not present or verified on this
delivered baseline. `fenced_transcript_source_acknowledgement` still acquires a
blocking graph lock and `_connect_index` may initialize schema through a SQLite
connection with a 30-second timeout. Final integrated Feature/Epic acceptance
therefore remains gated on Feature 5's bounded graph-lock and existing-index-only
repair being integrated and verified here. Pending UI presentation is not that
repair, and Feature 4 lifecycle state is not proof of it.

Feature 4's scoped browser navigation evidence remains distinct from its broader
documentation-refresh assertion. The scoped navigation passed; the broader
assertion remains unverified and is not cleared by this architecture browser
journey.

`architecture/design-mappings.json` still maps `cascade/recovery_progress` to
`cascade` despite the Recovery Progress design owning that directory. Epic
architecture reconciliation owns this mapping correction; this source/design
review does not claim it is resolved.

The earlier Task 1 publication failed and the Task 2 publication was reported
pending; neither is approval. This Task has no architecture-publication tool.
After the deliverable commit, the exact integrated revision must be routed to
the owning Feature architect for a fresh proposal/review. Until that owner
returns a successful review unit, this record claims source reconciliation and
local validation only, not architecture approval.
