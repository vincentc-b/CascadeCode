# Recovery and architecture closeout

## Delivered recovery contract

The existing `Recovery contract` remains the sole integration harness. Its real
temporary Git remotes and worktrees now provide complete accepted-merge and
post-merge-CI observations when the scripted forge reports a merge. This keeps
the source-green/changed-target, stale lifecycle copy, restart, split-root,
same-second source/cache, owner recovery and human-gate journeys on the same
production review, Task, Workspace and Watchdog adapters.

Epic closeout now fences every verified, blocker and terminal registry write by
the exact observed generation, review URL, source/target route and observation
identity. The comparison and write occur under the existing review registry
lock. A concurrent observation advance rejects the old writer, keeps the new
generation current and unverified, and makes closeout reacquire evidence. The
focused regression exercises all three writer classes and propagates the
rejected verified/terminal write to the caller.

Verified Epic receipts also fail closed at production, reload and presentation
boundaries. A new typed receipt requires exact accepted-merge CI policy and
newest generation-bearing results, matching observed target identity, equal
local and remote trunk heads, and both history and synchronization board proofs.
An incomplete legacy verified flag is downgraded during registry load; the
bounded War Room serializer independently marks incomplete green-CI or successful
sync claims unavailable and requests a fresh persisted observation.

## Verification

- `timeout --kill-after=10s 8m python -m pytest -q tests/test_late_repair_convergence.py tests/task/test_incident_budget.py tests/agent/test_provider_recovery_contract.py tests/test_review_publication_safeguards.py tests/test_review_recovery_journey.py tests/test_review_health.py tests/test_review_rebase.py tests/test_resolution_actions.py tests/watchdog/test_reservations.py tests/watchdog/test_audit_investigation.py tests/watchdog/test_parent_lifecycle_postcheck.py tests/feature/test_publication.py::test_review_recovers_remote_creation_before_local_registry_write --tb=short` — 202 passed with two existing multiprocessing `fork()` deprecation warnings in 371.06 seconds.
- `pytest -q tests/workspace/test_closeout_workspace.py tests/test_epic_review_state.py tests/boss/test_epic_complete.py` — 50 passed in 9.98 seconds. This includes duplicate-board refusal, detached-checkout cleanup, target movement, interrupted observation restart, split tracking ownership, clean fast-forward, dirty/diverged/wrong-branch preservation and the intervening Epic observation regression.
- `pytest -q tests/test_epic_review_state.py tests/war_room/test_open_reviews_api.py tests/boss/test_epic_complete.py --tb=short` — 64 passed in 17.76 seconds. This includes complete receipt round-trip and incomplete persisted/reloaded receipt refusal across the producer type, registry loader and passive War Room projection.
- `pytest -q tests/workspace/test_c4_source.py tests/workspace/test_c4_render.py::test_container_contract_is_immutable_offline_read_only_and_bounded` — 15 passed in 2.75 seconds.
- `pytest -q tests/workspace/test_c4_render.py::test_real_pinned_renderer_publishes_one_validated_handoff_and_cache tests/war_room/test_architecture_browsing_browser_journey.py::test_branch_architecture_is_pinned_navigable_and_refreshes_whole_snapshot --tb=short` — 2 passed in 194.37 seconds on the reconciled tree. It validated revision-pinned source, source symbols and declaration kinds, bounded rendering, warm artifact reuse, context → containers → components → Code, Level up, deep-link restoration and pinned-source opening.
- `git diff --check` passed.

An exploratory run that also selected the whole legacy
`tests/workspace/test_branch_synchronization.py` reported seven passes and
thirteen pre-existing fixture failures: twelve activation paths lack current
provider/model selection evidence and one old preflight expectation no longer
matches the active-repair contract. The scoped remote-trunk synchronization
suite above is green and covers this Feature's dirty/diverged/moved/split-root
contract. The legacy fixture gap is not hidden as acceptance evidence and was
not repaired by bypassing provider or approval gates.

No live forge was mutated and no full repository suite was run, matching the
declared boundary. Scripted forge transport proves adapter behavior, not live
credentials or hosted CI availability.

## Design and diagram reconciliation

Reviewed `DESIGN.md`, `cascade/DESIGN.md`, and
`cascade/{boss,workspace,watchdog,feature,war_room}/DESIGN.md` against the final
source. Shared review evidence remains owned by `cascade/DESIGN.md`; Boss owns
Epic closeout and the conditional writer use; Workspace owns fetched board proof
and safe operator synchronization; Watchdog owns bounded fresh observations;
Feature owns repair admission; War Room owns passive bounded presentation. The
root remains a link-level summary. Current-fact wording and existing behavior
diagrams already cover restart, target drift, owner recovery and read-only UI;
the shared and Boss designs describe the atomic fence, while Boss, Watchdog and
War Room now state the complete receipt and fail-closed presentation rules.

| Level / views | Final-diff result |
|---|---|
| `cascade-landscape`, `cascade-context` | Unchanged: no person, forge, provider, runtime or responsibility boundary changed. |
| `cascade-containers` | Unchanged: the existing local review registry, Git/forge and board paths remain; no process, store or isolation claim was added. |
| `cascade-supervisor-components`, `cascade-team-components`, `cascade-war-room-components` | Existing Boss/Workspace/Watchdog/Feature/Dashboard/HTTP responsibilities still describe the implemented interfaces. The change tightens one registry write inside the existing Boss/shared-review collaboration. |
| `cascade-boss-code` | Added `element.code.boss.epic-snapshot-write`, bound to `cascade/review.py::persist_epic_review_snapshot` as a Function under `element.component.boss`, plus verified and terminal caller relationships. `_merged_epic_review_landed` remains the proof join and its description now names complete exact CI and equal trunk heads. |
| `cascade-dashboard-code` | Existing `epic_review_snapshot_to_dict` node remains correctly bound as a Function under Dashboard; its description now records fail-closed completeness checks for CI, sync, board and observation evidence. |
| `cascade-workspace-code`, `cascade-watchdog-code`, `cascade-feature-code`, `cascade-war-room-http-code` | Source paths, symbols, kinds, component parents and relationships remain accurate. No implementation symbol changed in these owners. Workspace still supplies board/sync proof, Watchdog supplies the observation, Feature owns repair, and HTTP delegates to the shared passive projection. |
| Behavior | Boss and shared-review prose now state that verified, blocker and terminal writes compare generation, URL, route and observation identity under the registry lock; rejection preserves the newer unverified observation. |

The authoritative `model.dsl`, `views.dsl` and `workspace.contract.json` were
updated together. `cascade-boss-code` retains `cascade.codeComponent` ownership;
the new node has matching `cascade.parent`, `cascade.sourcePath`,
`cascade.sourceSymbol`, Function kind and contract identities. No accepted
snapshot was rewritten.
