# Task task_033_001_003 verification

Extended the existing Node DOM/browser-flow harness across Epic/Feature and
inline/tray placements. Both epic_028 branches, including cmt_010, are checked
on initial load with reversed API order; asynchronous arrivals extend to
cmt_012 and retain immediate parent context and exactly-once entries. Added
checks for whole-plan drafts, reply drafts, open details, resolve control
identity, resolved/outdated styling and placement. Existing cases cover focus,
scroll, hidden pause, reconnect coalescing, bounded backoff, single timers and
stale responses after page teardown/cache restoration. Added a hung-request
abort/deadline regression. Existing focused grouping cases cover cycles,
self-links, missing parents and timestamp ties without duplicating them.

Strengthened the HTTP/watchdog regression: one human post creates exactly one
CommentPosted event and one owning-team kickoff (each epic role once); five
subsequent GETs leave the event stream and delivered turn count unchanged.
The already mocked execution fixture now supplies deterministic provider
inventory at dispatch and execution boundaries, avoiding local credentials.

Supervised validation via Cascade swe_run_tests:

`pytest tests/war_room/test_plan_inline_threads.py tests/war_room/test_plan_render.py tests/war_room/test_comment_api.py tests/war_room/test_comment_resolve.py tests/workspace/test_human_comment_kickoff.py -q`

Result: **15 passed** (6.70s). Self-review: test-only changes, no storage/API or
runtime behavior changes and no additional framework.

Limitations: the existing DOM harness simulates browser events, timers, focus
and scroll; it does not measure real browser layout or network latency.
An exploratory run also included test_comments_api.py: its activation test
fails before posting because its separate fixture requires an authenticated
Cursor provider. That unrelated fixture was left unchanged; the scoped
HTTP/watchdog regression covers posting and refresh side effects with local
provider inventory. Initial supervised runs exposed this same credential
coupling in the kickoff fixture, corrected above.

The task-plan path is excluded by the Cascade commit guard; this report is retained alongside the scoped tests.
