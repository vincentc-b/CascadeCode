# Agent runtime design

Purpose: normalize provider discovery, credentials, model selection, role turns, and MCP transport. Interfaces are `run_role`/`RoleTurn`, capability preflight, planning sandboxes, and MCP wrappers used by tier graphs. Owns `REQ-AGENT-001` (bounded provider-neutral turns) and `DEC-AGENT-001` (capabilities are checked before launch).

Evidence: `cascade/agent/{adapter,preflight,planning_turn}.py`, discovery modules, and `tests/agent/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: provider-specific review provenance is incomplete in the pinned inventory.
