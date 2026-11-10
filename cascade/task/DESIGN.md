# Task execution design

Purpose: run one bounded implementation team in an isolated worktree with supervised file, test, commit, and lifecycle tools. Interfaces are Task graph/boot/wiring, SWE MCP, path guards, action recovery, lifecycle locks, and execution views. Owns `REQ-TASK-001` (implementation stays in assigned scope) and `DEC-TASK-001` (green post-commit supervised validation gates delivery).

Evidence: `cascade/task/`, `tests/task/`, and lifecycle tests at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: receipts are absent for many historical Tasks, including A-F handoff children.
