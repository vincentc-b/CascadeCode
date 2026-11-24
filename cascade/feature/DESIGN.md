# Feature team design

Purpose: run the persistent tactical team that decomposes Features, responds to review, and coordinates Task integration. Interfaces are Feature graph/boot/wiring, guarded Task creation, publication/review polling, comments, briefing, and branch recovery. Owns `REQ-FEATURE-001` (Feature context survives Task turnover) and `DEC-FEATURE-001` (Task writes and ancestor reads are guarded).




## Implementation and navigation

The [C4 team view](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/views.dsl) has key
`cascade-team-components`; the parent view is `cascade-supervisor-components`.
See the [cross-team execution diagram](../DESIGN.md#team-execution).
This team is a checkpointed LangGraph, not a separate operating-system service.
The lead and architect execute within the supervisor's bounded turn lifecycle.

```mermaid
flowchart LR
    Boot["boot.py: activation"] --> Graph["graph.py: ensure_feature_graph"]
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
| [repair.py](repair.py) | Persists generation-bound admission, idempotent authority, child identity, and delivery progress. |
| [role skills](../watchdog/role_skills.py) | Resolves the default playbooks, including design authoring/review. |

## Turn lifecycle

```mermaid
flowchart LR
    Start --> Ingest
    Ingest --> Lead
    Lead --> Architect
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

Verification: [graph and lifecycle tests](../../tests/feature/).

## Generation-bound late repair

`REQ-FEATURE-REPAIR-002`: [feature_repair](repair.py) records each request in the
existing action ledger before it emits `FeatureRepairAuthorized`. The event and
receipt bind one generation to the exact owner, active path, source/target refs,
and document digest. [Watchdog authorization](../watchdog/loop.py) admits the
active introduction only while all of those bindings and, after checkpointing,
the introducing commit and blob still agree.

```mermaid
sequenceDiagram
    participant Feature as feature_repair
    participant Ledger as executions.json
    participant Queue as Feature queue
    participant Board as Feature document
    participant Watchdog
    Feature->>Ledger: persist prepared generation
    Feature->>Queue: append FeatureRepairAuthorized once (exact bindings)
    Feature->>Board: commit exact active document
    Feature->>Ledger: checkpoint commit and blob
    Watchdog->>Ledger: rejoin live generation
    Watchdog->>Board: verify path, digest, commit and blob
    Note over Ledger,Queue: Restart joins the stable event ID before appending
```

The two roles run sequentially within each invocation. Their durable context survives child work turnover; the graph does not spawn a parallel role process for each node.

Libraries, provider/MCP wiring, and the precise sandbox boundaries are described in [Team libraries, wiring, and isolation](../DESIGN.md#team-libraries-wiring-and-isolation).

The integrated Structurizr code view is `cascade-feature-code`. From the supervisor components view, Explore **Feature team**; select a code node for its pinned source. This view is the navigable implementation structure; the diagrams above supplement it with lifecycle context.

## Child admission and recovery

`REQ-FEATURE-REPAIR-001`: Task recovery preserves direct-child scope and checks
current execution ownership before resuming delivery.
`DEC-FEATURE-REPAIR-001`: Use the existing supervised Task recovery and final
validation boundary; a Feature tool cannot declare its own merge successful.
[mint_task](mint.py) serializes child creation with the lifecycle lock and refuses
blocked parents. Ordinary active Features allocate and persist a child directly.
An active repair generation additionally requires its admitted request identity;
[reserve_repair_child](repair.py) stores the Task ID, request fingerprint and
rendered specification digest in `executions.json` before the Task or parent
document is written. Restart reuses that reservation, verifies an existing Task
against the digest, and idempotently repairs the parent child list and
`TasksMinted` event. A completed Feature cannot mint without first passing the
generation-bound repair admission and becoming the exact authorized active copy.
[recover_task](recovery.py) delegates to
[supervisor_recover_task_delivery](../task/supervisor_recovery.py).
Both entries appear in `cascade-feature-code`, linked from the scoped registry.
The [Boss closeout](../boss/DESIGN.md#delivery-and-closeout) and
[Workspace ownership](../workspace/DESIGN.md#work-ownership-and-retirement)
contracts govern the receiving parent and checkout. Failed target preflight
retains the Task; no graph checkpoint substitutes for delivery evidence.

```mermaid
sequenceDiagram
    participant Team as mint_task
    participant Action as feature_repair action
    participant Task as Task document
    participant Parent as Feature document
    Team->>Action: verify current action and reserve ID + digests
    Action-->>Team: same reservation on replay
    Team->>Task: write or verify exact backlog Task
    Team->>Parent: add child and breakdown idempotently
    Team->>Action: checkpoint child persistence
    Note over Action,Parent: A crash at either write resumes from the reservation
```
