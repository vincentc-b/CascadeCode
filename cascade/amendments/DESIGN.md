# Amendment design

Purpose: preserve Feature-to-Epic contract changes as stateful diff sidecars. Interfaces are `write_sidecar`, `read_amendment`, `update_amendment`, section replacement, and amendment logs. Owns `REQ-AMEND-001` (upward changes are explicit) and `DEC-AMEND-001` (section-scoped diffs are durable units).

Evidence: `cascade/amendments/` and `tests/amendments/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: unavailable reviews may contain rationale not recoverable from current code and tests.
