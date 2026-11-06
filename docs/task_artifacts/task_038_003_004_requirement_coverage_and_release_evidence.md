# task_038_003_004 — Requirement coverage and release evidence

Recorded 2026-11-06 for epic acceptance. Test names below are the durable
evidence; this artifact does not introduce a separate acceptance framework.

## Epic success-criteria mapping

| Criterion | Evidence |
| --- | --- |
| 1. Planning receives a minimal projection for every declared dependency. | `tests/test_dependency_projection.py::test_projection_represents_safe_lifecycle_outcomes_in_declared_order`; `tests/agent/test_planning_dependency_projection.py::test_epic_turn_projects_all_dependencies_without_content_access`; `tests/agent/test_planning_dependency_projection.py::test_feature_turn_projects_all_dependencies_without_content_access` |
| 2. Projection follows canonical merged-board lifecycle state and completed/unreadable dependencies satisfy it. | `tests/agent/test_planning_dependency_projection.py::test_synthetic_completed_dependency_is_projected_without_content_access`; `tests/test_dependency_behavior_compatibility.py::test_synthetic_canonical_completion_precedes_stale_registered_copy` |
| 3. Content authorization remains scoped and projection data is allowlisted. | `tests/agent/test_planning_dependency_projection.py::test_synthetic_completed_dependency_is_projected_without_content_access`; `tests/agent/test_dependency_refresh_tool.py::test_dependency_refresh_is_scope_bound_and_fresh_across_planning_transports`; `tests/test_dependency_projection.py::test_projection_source_failure_is_stable_safe_and_fail_closed` |
| 4. Content denial, unmet state, and unavailable status remain distinct. | `tests/agent/test_planning_sandbox.py::test_mint_feature_catalog_guidance_keeps_dependency_failures_distinct`; `tests/test_dependency_behavior_compatibility.py::test_dependency_evaluation_distinguishes_lifecycle_and_availability`; `tests/test_dependency_behavior_compatibility.py::test_dependency_evaluation_empty_list_and_source_failure` |
| 5. Readiness, actions, War Room live state, and transcript presentation agree while history stays history. | `tests/epic/test_plan_readiness.py::test_board_and_doc_read_models_match_commands`; `tests/war_room/test_planning_transcript.py::test_historical_blocker_does_not_override_synthetic_live_completion`; `tests/war_room/test_ui_render.py::test_dependency_status_ui_distinguishes_current_from_historical` |
| 6. Action boundaries recheck and refuse stale evidence. | `tests/test_planning_action_dependencies.py::test_action_refresh_ignores_cached_and_request_scoped_board`; `tests/test_planning_action_dependencies.py::test_synthetic_sign_off_succeeds_then_refuses_stale_success`; `tests/test_planning_action_dependencies.py::test_feature_approval_fails_closed_after_dependency_regresses`; `tests/test_planning_action_dependencies.py::test_mint_refreshes_owner_after_cached_dependency_regresses` |
| 7. Required lifecycle variants and compatibility gates are covered. | Completed/unreadable: synthetic projection test above. Readable/incomplete and missing: `test_dependency_evaluation_distinguishes_lifecycle_and_availability`. Source failure: `test_dependency_evaluation_empty_list_and_source_failure`. Tracking repository: `test_planning_documents_and_dependencies_are_owned_by_tracking_root`. Mid-turn completion: `test_readiness_and_sign_off_observe_dependency_completed_during_planning` and `test_mint_refreshes_owner_after_dependency_completes`. Stale-success refusal: criterion 6 tests above. Review/stacked behavior: `test_completed_dependency_does_not_replace_stacked_dispatch_gate` and `test_completed_feature_dependency_does_not_replace_task_review_gate`. |
| 8. The synthetic epic_034/epic_036 incident is locked as a regression. | The shared `synthetic_dependency_lifecycle` fixture drives `test_synthetic_canonical_completion_precedes_stale_registered_copy`, `test_synthetic_completed_dependency_is_projected_without_content_access`, `test_synthetic_sign_off_succeeds_then_refuses_stale_success`, and `test_historical_blocker_does_not_override_synthetic_live_completion`. Together they prove canonical epic_036 completion wins over its stale active copy, epic_034 cannot read its content, and planning/action/live status report satisfaction. |

## Feature acceptance checks

- Current versus historical status: the transcript remains verbatim and dated while
  the current UI summary is replaced from the refreshed structured board result.
- Canonical completion with unreadable content: the synthetic lifecycle fixture
  reports `satisfied` without making the dependency document readable.
- Failure distinctions: unmet lifecycle state, missing work, unavailable source, and
  content denial retain separate codes and explanations.
- Mid-turn refresh: readiness/sign-off and minting observe an incomplete dependency
  becoming complete without restarting the owning planning flow.
- Stale-success refusal: sign-off, feature approval, and minting refuse a dependency
  that regresses after turn-start evidence, without authorization-dependent writes.
- Existing readiness, review, and stacked-dispatch blockers remain independent of
  dependency satisfaction.

## Supervised results

Cascade `swe_run_tests` ran the acceptance-focused command:

```text
pytest tests/test_dependency_projection.py \
  tests/test_dependency_behavior_compatibility.py \
  tests/test_planning_action_dependencies.py \
  tests/agent/test_planning_dependency_projection.py \
  tests/agent/test_dependency_refresh_tool.py \
  tests/agent/test_planning_sandbox.py \
  tests/epic/test_plan_readiness.py \
  tests/war_room/test_planning_transcript.py::test_historical_blocker_does_not_override_synthetic_live_completion \
  tests/war_room/test_ui_render.py::test_dependency_status_ui_distinguishes_current_from_historical
```

Result: **61 passed in 12.38s**.

A broader diagnostic run collected 100 tests and produced 99 passes plus one
unrelated existing failure in
`test_completed_feature_awaiting_review_remains_in_active_lane`: its fixture refers
to absent `task_001`, causing recovery serialization to raise `unknown task
task_001`. The failure reproduces in isolation and is outside this dependency-status
change and the mapping above.
