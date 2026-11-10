# Probe design

Purpose: expose read-only repository/runtime readiness diagnostics. Interfaces are the probe CLI and structured results consumed by operators and smoke tests. Owns `REQ-PROBE-001` (diagnostics do not take lifecycle ownership) and `DEC-PROBE-001` (failures report evidence rather than mutate state).

Evidence: `cascade/probe/` and `tests/probe/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: historical review descriptions are not available for all probe changes.
