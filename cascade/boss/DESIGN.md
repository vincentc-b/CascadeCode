# Boss orchestration design

Purpose: coordinate cross-tier rollups, Task merges, completion gates, and operator status. Interfaces are the boss graph, `merge_task_branch`, completion/rollup handlers, orphan detection, and `BossView`. Owns `REQ-BOSS-001` (integration respects tier gates) and `DEC-BOSS-001` (merge authority stays outside ephemeral Task agents).

Evidence: `cascade/boss/` and `tests/boss/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: review-to-commit links remain ambiguous where forge descriptions were unavailable.
