# Epic team design

Purpose: run the persistent strategic team that owns Epic planning, decisions, approvals, and Feature coordination. Interfaces are Epic graph/boot/wiring, guarded tools, approvals, briefing/checkpoint state, and amendment reads. Owns `REQ-EPIC-001` (strategic context persists) and `DEC-EPIC-001` (Epic tools are scope-guarded).

Evidence: `cascade/epic/` and `tests/epic/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: exact child Task revisions for the A-F handoff remain unavailable.

## Readiness projection versus authorization

The board API calls `project_epic_plan_readiness` with its coherent response board
snapshot. This avoids one complete registered-worktree scan per visible unapproved
Epic. The public compute/require paths used for action authorization continue to
refresh dependencies and do not trust that UI snapshot, even when a caller supplies
a cached board. Both paths share the same readiness calculation and explanations;
only their evidence acquisition differs.
