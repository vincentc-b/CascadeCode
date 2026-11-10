# Task task_034_005_006 verification

The focused feature suite composes the real board, feature-comment, durable
event, Epic decision, architecture-lineage, scoped-hold, approval and
disposition entry points. It intentionally reuses the subsystem tests rather
than duplicating low-level serialization checks.

The integrated active-feature scenario creates a completed sibling, accepts its
architecture on the sibling branch, and merges that branch into the Epic
lineage. A material comment on a running sibling is delivered once to its
Feature Team and explicitly escalated once to the Epic Team, including on
retry. The Epic decision is relayed once in the originating open thread. Its
durable hold leaves the active task and branch state intact while rejecting
integration and premature release. The replacement proposal rebases on the
accepted sibling generation, receives fresh tuple-bound review and approval,
then releases only the affected scope; the accepted sibling and current
lineage pointer remain unchanged.

The backlog scenarios verify direct delivery to the active Epic Team with
feature/thread context, corrective work with explicit accepted-work
dependencies and no inherited human approval, and an unsafe restart represented
as an actionable durable human blocker without returning accepted or open work
to backlog.

Scoped validation command:

`pytest -q tests/comments/test_handoffs.py tests/comments/test_impact_decisions.py tests/workspace/test_scoped_change_holds.py tests/workspace/test_architecture_review.py tests/comments/test_change_dispositions.py`

Pre-commit result: **49 passed** (28.53s).

Known limits: these deterministic repository scenarios do not exercise the War
Room presentation layer. Existing comment and architecture UI suites own visual
rendering; Feature C owns the broader split-repository promotion recovery
matrix. Human thread resolution remains deliberately manual.
