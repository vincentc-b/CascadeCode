# Agent runtime design

Purpose: normalize provider discovery, credentials, model selection, role turns, and MCP transport. Interfaces are `run_role`/`RoleTurn`, capability preflight, planning sandboxes, and MCP wrappers used by tier graphs. Owns `REQ-AGENT-001` (bounded provider-neutral turns) and `DEC-AGENT-001` (capabilities are checked before launch).

Evidence: `cascade/agent/{adapter,preflight,planning_turn}.py`, discovery modules, and `tests/agent/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: provider-specific review provenance is incomplete in the pinned inventory.

## Cold MCP startup and repository context

Planning and task MCP entry points must initialize in a fresh Python process,
without depending on the supervisor's import order. The repository-context
bridge imports board/workspace dependencies inside its functions: eager package
initialization can traverse workspace, watchdog, task tools, and return to the
partially initialized bridge before its exports exist. This previously prevented
Epic 044's Manager and Architect from starting any planning or audit turn.

This import boundary does not change trusted configuration, split target/tracking
repository authority, architecture destination, or tool permissions. Startup
coverage must exercise actual stdio subprocesses, including initialization and
tool discovery, plus split-repository tool calls; in-process imports alone can
hide the cycle. After fixing an initialization failure, resume the existing team
through its durable queue rather than approving or authoring its plan externally.
