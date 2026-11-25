# Post-push replay and original-budget closeout

## Implemented proof

The real-repository late-repair journey now binds the queued Task action's
original incident budget before recovery for both colocated and split
product/tracking roots. It interrupts `ensure_feature_review` after the bare
remote accepts the exact Feature ref and the scripted forge creates the review,
but before the immutable local review generation is stored. Before replay, the
harness independently reads the bare remote ref and forge source/target snapshot.

Unavailable forge discovery and changed forge source evidence leave the local
generation absent, retain the incident's accountable owner and selected next
capability, and create no second review. Exact evidence resumes through the
normal Feature completion/publication path under competing callers. Repeated
publication, acceptance, Task-merge and incident-postcheck sweeps retain one
review, one accepted generation, one resolved receipt and one remote Feature-ref
effect. The post-receive hook observes exactly one
`refs/heads/feat/feat_001` update in each root layout. The existing accepted
target journey remains one Epic-ref effect for split roots and three for the
colocated lifecycle path; later sweeps add none.

Production replay now snapshots a discovered review before converting a prior
remote effect into a local generation. It requires an open state and exact
source/target refs and heads. A route-shaped review alone is insufficient.
Watchdog budget settlement now treats a normally completed deferred, refused or
no-op adapter invocation as a charged completed invocation, while lifecycle
resolution remains the independent postcheck's decision. Execution errors and
unsafe results retain failure semantics.

## Public budget snapshots

Every snapshot is read through `read_incident_budget`; the test does not edit the
ledger. Identity, original action, admission time, policy, owner and bindings are
equal throughout. The finite version-1 default allowance includes six tool
attempts, six paid turns, 1,800 process seconds, 1,800 model seconds, a 3,600
second elapsed deadline and 200,000 known tokens.

| Observation | Tool attempts charged | Operation receipts | Status |
| --- | ---: | ---: | --- |
| Original bind | 0 | 0 | active |
| Recovery adapter completion | 1 | 1 | active |
| Post-push reservation reconciled | 2 | 2 | active |
| Runtime bootstrap | 2 | 2 | active |
| Worker restart | 2 | 2 | active |
| Final independent postcheck | 2 | 2 | active |
| Exact remainder settled | 6 | 3 | exhausted |

Replaying the publication operation returns its existing receipt and replaying
settlement reports `operation_already_settled`. Exhaustion retains one stable
escalation ID and `bounded_extension_required`; a further expensive recovery is
refused without adding an operation, changing the original incident/action, or
removing prior receipt history.

## Design and architecture reconciliation

Reviewed `cascade/DESIGN.md`, `cascade/watchdog/DESIGN.md`,
`cascade/task/DESIGN.md`, the root/Workspace/Feature designs, and the pinned
`model.dsl`, `views.dsl` and `workspace.contract.json`. The Cascade design now
states the post-push discovered-review evidence rule, and the Watchdog design
states adapter-invocation settlement semantics. Task's owned incident-budget API
and policy did not change.

No C4 source edit is required. The existing `cascade-boss-code` view already
binds `ensure_feature_review` and `_require_repair_review_route`; the existing
`cascade-watchdog-code` view binds `record_result` and the Task-owned reserve /
settle consumers, with correct Function kinds, source paths, component parents
and relationships. Landscape, context and containers have no changed person,
external system, process, data store or isolation boundary. Components retain
the same Boss publication and Watchdog admission responsibilities. The code
change is inside those already modeled functions.

## Verification

- `pytest tests/test_late_repair_convergence.py::test_watchdog_owner_repair_delivers_and_independently_verifies_once -q --tb=short`
  — 2 passed in 77.60s; both root layouts, two real worker PIDs, one Feature-ref
  effect each, public budget snapshots and exhaustion.
- `pytest tests/test_feature_closeout_flow.py::test_review_open_toast_is_linked_idempotent_and_restart_safe tests/test_feature_closeout_flow.py::test_saved_review_retries_linked_toast_after_append_failure tests/test_review_publication_safeguards.py tests/watchdog/test_reservations.py -q --tb=short`
  — 35 passed in 9.49s.
- `pytest tests/workspace/test_c4_source.py tests/workspace/test_c4_render.py::test_real_pinned_renderer_publishes_one_validated_handoff_and_cache tests/war_room/test_architecture_browsing_browser_journey.py -q --tb=short`
  — 17 passed in 179.37s. Source validation and the real renderer checked every
  authored symbol/kind/binding, including the unchanged Boss and Watchdog Code
  nodes. The supported browser journey verified context → containers →
  components → Code, Level up, deep-link restoration and pinned-source opening.
- `git diff --check` — passed.

The forge remains a deterministic scripted transport as authorized by the Task;
Git repositories, pushes, subprocess worker bootstrap/restart, production owner
APIs, durable stores and postchecks are real. No live deployment, dependency
installation or accepted architecture snapshot rewrite was performed.
