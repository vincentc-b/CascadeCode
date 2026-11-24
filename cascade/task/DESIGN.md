# Task execution design

Purpose: run one bounded implementation team in an isolated worktree with supervised file, test, commit, and lifecycle tools. Interfaces are Task graph/boot/wiring, SWE MCP, path guards, action recovery, lifecycle locks, and execution views. Owns `REQ-TASK-001` (implementation stays in assigned scope) and `DEC-TASK-001` (green post-commit supervised validation gates delivery).



## Interrupted review publication attempts

Review-rebase attempts claimed through `resume_action` additionally persist the
owning process identity. `reconcile_abandoned_review_publications` runs before the
watchdog reads team boards, so a malformed conflict resolution cannot hide a dead
publication owner. Under the existing reentrant lifecycle lock it verifies death,
enqueues a claim-specific `BranchActionRecoveryRequested` before committing the
state transition, and closes the unfinished attempt as `owner_decision`. Replay
checks the stable event identity. Completed attempt history is preserved and the
same logical action is reused. Live, inaccessible and legacy-unidentified owners
are not reclaimed. This path does not retry Git or assert that a local merge commit
was published; the team must inspect the preserved checkout and remote evidence.
See `cascade/DESIGN.md` for publication validation and timeout requirements.


## Implementation and navigation

The [C4 team view](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/views.dsl) has key
`cascade-team-components`; the parent view is `cascade-supervisor-components`.
See the [cross-team execution diagram](../DESIGN.md#team-execution).
This team is a checkpointed LangGraph, not a separate operating-system service.
The SWE execute within the supervisor's bounded turn lifecycle.

```mermaid
flowchart LR
    Boot["boot.py: activation"] --> Graph["graph.py: ensure_task_graph"]
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
    Ingest --> SWE
    SWE --> End
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

Verification: [graph and lifecycle tests](../../tests/task/).

Task graphs use one SWE node. Delivery additionally passes supervised validation and integration gates in [graph.py](graph.py); checkpoint cleanup is explicit in [checkpoint.py](checkpoint.py).

Libraries, provider/MCP wiring, and the precise sandbox boundaries are described in [Team libraries, wiring, and isolation](../DESIGN.md#team-libraries-wiring-and-isolation).

The integrated Structurizr code view is `cascade-task-code`. From the supervisor components view, Explore **Task team**; select a code node for its pinned source. This view is the navigable implementation structure; the diagrams above supplement it with lifecycle context.

## Durable delivery collaborators

`cascade-task-code` exposes [resume_action](action_recovery.py),
[execution_lease_is_live](execution.py), and [swe_run_tests](git_tools.py)
alongside the graph and tool registry.
The action ledger in tracking-root `.cascade/executions.json` preserves attempts,
claims and final validation evidence across worker restart. Recovery retains the
Task identity and checks live execution ownership. [Boss](../boss/DESIGN.md#delivery-and-closeout)
consumes the validated source/target pair; [Workspace](../workspace/DESIGN.md#work-ownership-and-retirement)
checks the receiving parent. Source or target movement requires the supervised
validation workflow, not a manually edited queue record.
When a current repair action owns the Task, the queued delivery metadata also
stores that action ID, generation, and Feature ID. This joins the exact green
pair to its repair obligation without changing the stable queued-action ID.
The same queue operation advances the matching repair receipt to
`delivery_pending`; replay retains the original Task and repair identities.

`REQ-TASK-DELIVERY-002`: A queued delivery is valid only for its exact Task
source and Feature target heads. [retry_pending_task_merges](../task_rollup.py)
uses branch synchronization before
[_request_delivery_revalidation](../task_rollup.py) withdraws stale scheduling,
records the replacement pair, and queues the original Task for supervised final
validation. The old validation and every action attempt remain in the ledger;
only a later green result may replace the current queue evidence.

```mermaid
flowchart LR
    Queue[Queued Task action + green pair] --> Compare[Read source and target heads]
    Compare -->|exact| Merge[Boss merge gate]
    Compare -->|moved| Sync[Guarded branch synchronization]
    Sync -->|refused| Retain[Retain checkout, action and old evidence]
    Sync -->|clean| Retry[Queue exact replacement pair for supervised tests]
    Retry -->|green| Queue
    Retry -->|red or interrupted| Retain
```
