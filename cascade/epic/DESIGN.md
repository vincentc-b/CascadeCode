# Epic team design

Purpose: run the persistent strategic team that owns Epic planning, decisions, approvals, and Feature coordination. Interfaces are Epic graph/boot/wiring, guarded tools, approvals, briefing/checkpoint state, and amendment reads. Owns `REQ-EPIC-001` (strategic context persists) and `DEC-EPIC-001` (Epic tools are scope-guarded).



## Readiness projection versus authorization

The board API calls `project_epic_plan_readiness` with its coherent response board
snapshot. This avoids one complete registered-worktree scan per visible unapproved
Epic. The public compute/require paths used for action authorization continue to
refresh dependencies and do not trust that UI snapshot, even when a caller supplies
a cached board. Both paths share the same readiness calculation and explanations;
only their evidence acquisition differs.


## Implementation and navigation

The [C4 team view](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/views.dsl) has key
`cascade-team-components`; the parent view is `cascade-supervisor-components`.
See the [cross-team execution diagram](../DESIGN.md#team-execution).
This team is a checkpointed LangGraph, not a separate operating-system service.
The manager and architect execute within the supervisor's bounded turn lifecycle.

```mermaid
flowchart LR
    Boot["boot.py: activation"] --> Graph["graph.py: ensure_epic_graph"]
    Wiring["wiring.py: role execution"] --> Graph
    Graph --> State["state.py: graph state"]
    Graph --> Registry["registry.py: scoped tools"]
    Graph <--> Checkpoint["checkpoint.py: SQLite saver"]
    Graph --> Runtime["agent runtime / provider turn"]
```

| Implementation | Responsibility |
|---|---|
| [boot.py](boot.py) | Seeds activation context and model selections. |
| [graph.py](graph.py) | Compiles the graph, ingests events, and executes role turns. |
| [state.py](state.py) | Defines checkpointed role, message, and queue state. |
| [checkpoint.py](checkpoint.py) | SQLite state under `.cascade/checkpoints/<work-id>.sqlite`; thread ID is the work ID. |
| [registry.py](registry.py) and [wiring.py](wiring.py) | Scoped tool registration and execution wiring. |
| [role skills](../watchdog/role_skills.py) | Resolves the default playbooks, including design authoring/review. |

## Turn lifecycle

```mermaid
flowchart LR
    Start --> Ingest
    Ingest --> Manager
    Manager --> Architect
    Architect --> End
    End["End of this invocation"]
```

Ending an invocation does not mean the work item is complete. Later events resume
the work's graph state. Queue offsets prevent already consumed events from being
treated as new input. Checkpoints retain execution context; Markdown work state,
Git history, and durable action receipts remain the delivery evidence.

Provider failures, tool authorization failures, and blocked review gates do not
authorize advancing lifecycle state. Recovery inspects durable state and the
preserved worktree before resuming the owning team. See
[shared supervision](../team_supervision.py) and
[branch recovery](../team_branch_recovery.py).

Verification: [graph and lifecycle tests](../../tests/epic/).

The two roles run sequentially within each invocation. Their durable context survives child work turnover; the graph does not spawn a parallel role process for each node.

Libraries, provider/MCP wiring, and the precise sandbox boundaries are described in [Team libraries, wiring, and isolation](../DESIGN.md#team-libraries-wiring-and-isolation).

The integrated Structurizr code view is `cascade-epic-code`. From the supervisor components view, Explore **Epic team**; select a code node for its pinned source. This view is the navigable implementation structure; the diagrams above supplement it with lifecycle context.

## Immediate-child recovery

`cascade-epic-code` links the scoped registry to
[recover_feature](recovery.py) and
[supervise_child](../team_supervision.py). The adapter requires the immediate
parent relationship and returns an already-running outcome for a live team.
For a direct Feature owning a completed-parent Task mismatch,
[_recover_feature_lifecycle_mismatch](../team_supervision.py) verifies the exact
registered owner, direct Task relationship, and current durable generation,
then calls Feature `recover_task`. That call selects the same `feature_repair`
inspect/admit/resume operation used by Feature self-recovery. Its result keeps
request, acknowledgement, execution, verification, refusal, and next
prerequisite separate. A live Feature graph remains an expected wait and does
not enqueue or claim repair.

For other Feature incidents, supervision queues a generation-keyed message and
wakeup. [The package contract](../DESIGN.md#delivery-and-review-boundaries)
distinguishes that coordination acknowledgement from executable lifecycle
repair. Durable Feature-repair actions and queued delivery attempts survive
restart; replay rechecks the same owner and generation before mutation.

```mermaid
sequenceDiagram
    participant Epic as recover_feature
    participant Supervision as supervise_child
    participant Feature as recover_task
    participant Repair as feature_repair
    Epic->>Supervision: direct Feature + recover
    Supervision->>Supervision: verify owner, Task parent, generation
    alt live Feature owner
        Supervision-->>Epic: expected wait
    else exact mismatch
        Supervision->>Feature: expected mismatch generation
        Feature->>Repair: inspect then admit/resume
        Repair-->>Epic: executed/refused; verified remains separate
    else other incident
        Supervision-->>Epic: durable handoff acknowledgement
    end
```

Verification: [immediate parent recovery](../../tests/epic/test_parent_lifecycle_recovery.py).
