# Agent runtime design

Purpose: normalize provider discovery, credentials, model selection, role turns, and MCP transport. Interfaces are `run_role`/`RoleTurn`, capability preflight, planning sandboxes, and MCP wrappers used by tier graphs. Owns `REQ-AGENT-001` (bounded provider-neutral turns) and `DEC-AGENT-001` (capabilities are checked before launch).

## Implementation and navigation

The [package component index](../DESIGN.md#architecture-navigation) connects
`cascade-context` → `cascade-containers` → `cascade-supervisor-components` →
`cascade-agent-code`, owned by `element.component.agent`. The authoritative
[model](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/model.dsl)
and [views](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/views.dsl)
contain real implementation declarations; the sequence below supplements them.

| Entry point | Responsibility and boundary |
|---|---|
| [run_planning_role_turn](graph_turn.py) | Resolve checkpointed role/provider/model selections, recheck capability and call the tier runner. Tier graphs own checkpoints. |
| [_run_sandbox_turn](planning_turn.py) / [PlanningSandbox](planning_sandbox.py) | Use the assigned team checkout, construct scoped tools and collect tool effects; clean up per-turn scratch files. |
| [dispatch_planning_tool](mcp_wrappers.py) | Dispatch through the role catalog and owning tier's guard. A tool result establishes only that operation's outcome. |
| [RoleTurn / RoleResult](types.py) | Carry launch settings, text/status, tool effects and optional provider recovery report. No normalized usage receipt is present. |
| [run_role](adapter.py) | Suppress terminal reconciled launches, check installation/credentials, register a live turn and dispatch Cursor, Claude, Codex or the test provider. |
| [run_codex_role](codex_cli.py) / [run_subprocess_turn](cli_common.py) | Check CLI tool-host support, pass per-turn MCP settings and execute the CLI. Unsupported tool hosting fails before the repair turn. |
| [register_turn / cancel_live_turns](turn_registry.py) | Track in-process task/PID identities and request cancellation during worker drain. This registry is not a durable incident ledger. |
| [report_provider_recovery](recovery_contract.py) | Preserve action/checkpoint identity in the provider result. A completed provider turn does not establish the original incident's postcondition. |

```mermaid
sequenceDiagram
    participant Graph as Tier graph / durable checkpoint
    participant Planning as Planning runner / scoped tools
    participant Adapter as run_role
    participant Provider as Provider transport
    participant Owner as Owning tool adapter / durable action
    Graph->>Planning: Authorized role inputs and recovery evidence
    Planning->>Adapter: RoleTurn
    alt Reconciled terminal recovery
        Adapter-->>Planning: No-launch result
    else Eligible turn
        Adapter->>Adapter: Provider and credential checks; register live turn
        Adapter->>Provider: Launch with scoped tool configuration
        Provider->>Owner: Production tool request
        Owner-->>Provider: Guarded result or precise refusal
        Provider-->>Adapter: Text and process status
        Adapter-->>Planning: RoleResult with recovery identity
    end
    Planning-->>Graph: Result and tool effects; remove scratch
```

## State, failure and isolation

`DEC-AGENT-001` keeps capability checks ahead of provider launch so an unavailable
tool host cannot silently substitute an unguarded workflow. Planning and SWE
callers retain their separate tier catalogs and guards. `PlanningSandbox` selects
a working directory and temporary files; it does not create OS isolation.
Provider permission mode controls provider-level restrictions, and `yolo`
explicitly disables optional provider sandboxing. MCP guards cannot constrain
arbitrary provider shell access. A C4 component is not a security sandbox.

The CLI helper uses a 3,600-second default timeout and kills/reaps the direct
process on timeout. The live registry cancels its asyncio task and signals its
recorded PID on drain. These mechanisms do not establish a hard bound on all
descendant processes or remote provider spending. There is no durable cumulative
incident usage reservation in this boundary; token consumption is not available
through `RoleResult`. Review validator process-group cleanup is a separate
[publication contract](../DESIGN.md#review-publication-safeguards).

Tier graph checkpoints and the [Task action ledger](../task/DESIGN.md) retain
recovery identity across restart. Live-turn entries and scratch effects are not
restart authority. Recovery callers reconcile durable action/effect evidence
before launching again; a lost response does not justify replaying a mutation.
Missing credentials, failed capability checks and tool refusals remain failures
or named prerequisites. Independent incident verification belongs to the
[Watchdog](../watchdog/DESIGN.md#recovery-admission-and-active-path-authority).

Verification references: [provider recovery](../../tests/agent/test_provider_recovery_contract.py),
[CLI transport](../../tests/agent/test_claude_codex_cli.py),
[planning scope](../../tests/agent/test_planning_sandbox.py), and
[worker drain](../../tests/workspace/test_feat_018_002_drain_integration.py).

## Cold MCP startup and repository context

Planning and task MCP entry points must initialize in a fresh Python process,
without depending on the supervisor's import order. The repository-context
bridge imports board/workspace dependencies inside its functions: eager package
initialization can traverse workspace, watchdog, task tools, and return to the
partially initialized bridge before its exports exist. Lazy imports keep planning
and audit entry points independent of package initialization order.

This import boundary does not change trusted configuration, split target/tracking
repository authority, architecture destination, or tool permissions. Startup
coverage must exercise actual stdio subprocesses, including initialization and
tool discovery, plus split-repository tool calls; in-process imports alone can
hide the cycle. After fixing an initialization failure, resume the existing team
through its durable queue rather than approving or authoring its plan externally.
