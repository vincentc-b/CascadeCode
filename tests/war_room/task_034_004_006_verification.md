# Task task_034_004_006 verification

The focused acceptance suite composes Feature D's existing payload, browser,
comment API, semantic-anchor and lifecycle-scope checks instead of repeating
Feature B's renderer validation or Feature C's broad promotion matrix.

The browser-flow harness verifies cross-repository revision labels beside the
proposal summary; one shared view, level, selection and history; current- and
proposed-side element/relationship selection; two parallel same-label
relationships distinguished only by semantic ID; drill and back; every changed
view; explicit added and removed counterparts; first, empty, removed, unchanged
and error presentations; requirements, decisions and source/model/plan diff
content; and actionable unsupported-interaction feedback.

The Python checks retain the authoritative API and lifecycle evidence: exact
key/level pairing and pinned revisions, added/removed/first/empty/unchanged/error
payloads, all four immutable semantic anchor kinds and original links, outdated
targets remaining blocking until authorized resolution, direct and dependent
holds without unrelated-work leakage, owner-subtree fallback, and all approval,
dispatch, integration, merge and closeout boundaries. Feature C's architecture
review suite remains the authority for exact reviewed-revision invalidation.

Scoped validation command:

`pytest -q tests/workspace/test_c4_review.py tests/workspace/test_c4_threads.py tests/workspace/test_semantic_blocking_scope.py tests/workspace/test_architecture_review.py tests/war_room/test_paired_c4_review_ui.py tests/war_room/test_comment_api.py`

Pre-commit result: **63 passed** (23.64s).

Known limitations: the browser harness exercises the production navigation and
rendering module with a deterministic DOM rather than measuring native browser
layout. Diagram geometry and exporter correctness remain covered by Feature B;
promotion recovery remains covered by Feature C. Freehand/pixel annotation and
general diagram editing are intentionally outside Feature D.
