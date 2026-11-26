# Feature transcript architecture planning review

The committed feature plan at `ba53aa47ac3fb433d4110228fc09baa5a3c05746`
specifies the future fenced transcript, receipt consumer, reply identity and
bounded history API. No product source, `DESIGN.md` or C4 model changed in this
feature planning branch. The current War Room design accurately describes the
full JSONL read, process-local append fence and author/body backfill; the
planned behavior is assigned to the four implementation tasks.

## Design and diagram impact

| Level | Current review and assigned update |
|---|---|
| `cascade-context`, `cascade-containers` | Operator, repository and in-process War Room/supervisor boundaries remain accurate. Task 4 checks these relationships against final code. |
| `cascade-war-room-components`, `cascade-dashboard-code` | Current transcript ownership is accurate. Tasks 1–4 add source-verified fence, replay, reply and page/route nodes as their code lands. |
| `cascade-team-components`, `cascade-task-code` | Task 2 verifies post-commit notifications and acknowledgement without a source lock under the graph fence. |
| `cascade-supervisor-components`, `cascade-watchdog-code`, `cascade-workspace-code` | Task 2 owns bounded drain and route handoff; Task 3 owns checkpoint lineage and role-return identity. |
| `cascade-teams-code` | Task 3 checks Epic/Feature persisted message identity against actual checkpoint symbols. |
| Behavioral flow | The feature plan has the proposed append/replay sequence. Tasks reconcile normal execution, exact-tail repair, ambiguous routing and restart in the owning designs. |

Reviewed `DESIGN.md`, `cascade/DESIGN.md`,
`cascade/war_room/DESIGN.md`, `cascade/task/DESIGN.md`,
`cascade/watchdog/DESIGN.md`, `cascade/workspace/DESIGN.md`, and the
`model.dsl`, `views.dsl` and `workspace.contract.json` source contract. The
War Room design links its real `chat_store.py`, `planning_transcript.py` and
`sidecar_routes.py` entry points and the context → containers → component →
native Code path. Current source confirms `process_lock` in read/append/sync;
this is a documented limitation, not a cross-process guarantee. The normal
path is graph checkpoint → role return → direct append → historical GET. A
return-to-append interruption currently needs explicit checkpoint sync, whose
author/body comparison can coalesce separate same-text replies. These paths
justify the Task 1 fence and Task 3 stable identity requirements.

`python -m pytest -q tests/workspace/test_c4_source.py` passed (14 tests);
`git diff --check` passed. The Epic's pinned architecture evidence records a
successful local render and browser path for the unchanged model. This review
does not claim the proposed transcript crash matrix has passed.

Task 1 was already active when this review started. Its Implementation notes
contain the necessary fence, migration, crash and C4 obligations, but its
Acceptance criteria and Test plan remain `TBD`, and its Parent Feature link is
stale. A message to `task_049_002_001` requested correction through Cascade
before delivery. Task 4 still owns the integrated Code navigation, source
opening, warm reuse and render-bound acceptance checks. Implementation must
publish its own updated design/model review after source reconciliation.

Cascade published that exact request as `no_diagram_change`, operation
`architecture-publication-37503fff31186b6fcfc3b617a7b6b624efe74912b24c6eae7de4e0cf20ee20a7`,
review unit
`architecture-review-af284c3d92d04c7e54f5cb37094de52bec422fdfaa24bb8dd633f923efe22916`.

## Current plan revision review

The committed plan at `ac9ddcf32cd67965da38682847f59e183f78b1d7`
adds the pinned producer revision and fixture checks, the durable
receipt-to-message acknowledgement and publisher mapping, and the oversized
legacy-row detail route. Task 2 and Task 4 acceptance criteria carry those
interfaces and their Watchdog/War Room Code-view obligations. The branch diff
since the initial publication changes only work records; no source, design,
model, views or source contract changed. The reviewed current-design paths
above remain accurate. This is a `no_diagram_change` planning decision for
`cascade-context`, `cascade-containers`, `cascade-war-room-components`,
`cascade-dashboard-code`, `cascade-task-code`, `cascade-watchdog-code`,
`cascade-workspace-code` and `cascade-teams-code`; the implementation tasks
must update affected views after the code lands. The exact current-plan
publication request is in `feat_049_002_architecture_review.json`.

Cascade published the current pinned request as `no_diagram_change`, operation
`architecture-publication-af47d78d2bb5cc4b2220cf040485c982a5c6a3b53cb5ddc3a0d00765fe09b4f4`,
review unit
`architecture-review-a5daa55cf2f6366eb91d015f184c98fcf337129c34dc00072747c6a11176144d`.
The request JSON parsed and `git diff --check` passed. No current-design edit
or model render was needed for this documentation-only revision. Task 1's
`TBD` acceptance and test plan remain an open child-delivery correction.
