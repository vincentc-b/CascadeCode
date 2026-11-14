# War Room design

Purpose: expose the loopback operator UI/API for status, approvals, chat attachment, review, recovery, and diagnostics. Interfaces are `serve`, route modules, serializers/views, authenticated human actions, and static/template assets covered by this owner. Owns `REQ-WARROOM-001` (operator actions are explicit) and `DEC-WARROOM-001` (the UI projects canonical services rather than owning state).

Evidence: `cascade/war_room/` and `tests/war_room/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: unavailable forge descriptions limit historical attribution. Local
audit fixtures do not establish post-deployment live acceptance.

## Bounded health-audit projection reads

`REQ-WARROOM-AUDIT-001`: Dashboard consumers read only the current projection
pointer, its one immutable manifest, and the requested current, coverage, or
history pages. Regular-file no-follow opens cap total source bytes at 1 MiB,
rows at 100, and the serialized result at 256 KiB. Missing, stale, corrupt,
incompatible, or wrong product/tracking evidence is typed `pending`; it never
becomes an empty healthy result.

`DEC-WARROOM-AUDIT-001`: `audit_projection_reader.py` validates the bounded
manifest header and each page it actually visits instead of calling the
producer's full-epoch validator. Filters are normalized exact work ID, owner,
verification status, and UTC occurrence bounds. Opaque cursors bind those
filters to section, epoch, page, and row offset and contain no path. A newer
pointer returns an explicit epoch restart. Budget exhaustion returns an
incomplete page and continuation while preserving producer `source_ref`,
legacy provenance, and `detail_truncated` without opening a recovery ledger.

## Refresh latency and coherent read projections

`REQ-WARROOM-REFRESH-001`: first board rendering must not wait for independent
flight, boss, chat, audit or provider panels. The board and pending-brief
cancellation lookup run concurrently, but both must finish before board actions
are enabled; cancellation safety is not traded for responsiveness. Optional panel
requests no longer delay startup polling. Existing forced post-action freshness and
single-flight board reads remain intact.

`DEC-WARROOM-REFRESH-001`: serialize Epic readiness from the same request-scoped
board snapshot used for the rest of the response. `project_epic_plan_readiness`
is explicitly a read projection; it does not refresh all registered worktrees per
Epic. `compute_epic_plan_readiness` and approval/sign-off/dispatch boundaries still
fetch authoritative dependency evidence independently of a supplied or cached board.
A UI snapshot is never permission to execute a lifecycle action.

Cold scans parse thousands of frontmatter records across retained worktrees. The
board parser prefers PyYAML's `CSafeLoader` when libyaml is available and falls back
to `SafeLoader`; both retain safe-constructor semantics, schema validation, dates,
round-trip behavior and rejection of Python object tags. This is parser acceleration,
not an additional stale-state cache or a relaxation of document validation.

Regression evidence: `tests/epic/test_plan_readiness.py` verifies no per-Epic fresh
scan in board serialization while authorization still refreshes; board parser
compatibility and unsafe-tag rejection are covered in `tests/board/test_parse.py`.
The refresh race harness covers cancellation lookup, optional-panel independence,
and forced post-action reads.

Board serialization also batches completed-Epic staging checks into one integration
registry snapshot, and shares one durable recovery-action snapshot between incident
and task-delivery projections. These snapshots live only for that response; the next
request rereads the registries, and existing locks and standalone action-boundary
reads remain unchanged. `tests/war_room/test_projection_batching.py` verifies the
read count, empty snapshots, and refresh across requests.

## Health-audit HTTP consumer

`REQ-WARROOM-AUDIT-002`: `GET /api/health/audit` exposes verified current incidents,
producer-published aggregate coverage, freshness, and bounded receipt/failure
metadata. `GET /api/health/audit/coverage` and `/api/health/audit/history` serve
epoch-pinned pages with a default of 50 and maximum of 100 rows. Exact work ID,
owner, status, and UTC occurrence-time filters preserve unknown and unverifiable
evidence as nonmatches. Malformed query input is a 400; a changed epoch or cursor
filter mismatch gives a bounded restart response. Each response names the epoch,
continuation, and completeness, stays within 256 KiB serialized bytes, and
preserves stable source references instead of reading large raw details. An empty
verified-current page with incomplete coverage does not claim health.

`DEC-WARROOM-AUDIT-002`: GET routes use the
[bounded projection reader](#bounded-health-audit-projection-reads)
at the resolved product repository root. They do not inspect recovery ledgers,
canonical board/worktrees, Git, providers, or schedule audit/recovery work.
`POST /api/health/audit` remains the authenticated manual admission route.
Repository identity, freshness and read-budget failures are visible as pending or
unknown status. The shared boundary is owned by
[the package design](../DESIGN.md#health-audit-read-boundary).

Verification locations: [route tests](../../tests/war_room/test_health_audit_routes.py)
and [reader tests](../../tests/war_room/test_audit_projection_reader.py) cover filtered pagination,
epoch/filter restart, stale and corrupt evidence, and strict source/response
budgets. The [integrated fixture](../../tests/war_room/test_audit_integrated_experience.py) follows real
producer output through the loopback routes across a new epoch and split
product/tracking roots, while the [browser race harness](../../tests/war_room/war_room_refresh_races.mjs) verifies
single-flight, read-only browser refreshes. The [GET benchmark](../../tests/war_room/benchmark_audit_get.py)
records warm loopback GET p95 and actual source/response bytes for a representative
10,000-attempt fixture. Local smoke evidence is not post-deployment acceptance.

## Feature activation explanations and new-work attention

`REQ-WARROOM-READINESS-001`: Activation explanations preserve `approved` and
`blockers` consumers. The board exposes a versioned summary, reasons, satisfied
prerequisites, owners, existing actions, observation freshness and actual dispatch
attempt evidence when available. A fresh human-action blocker takes precedence,
followed by unknown required evidence, known work/system waits, and evaluated
readiness awaiting dispatch. Passing gates never claims execution; historical
refusals remain separate from a newer evaluation. The browser renders these
projections without implementing eligibility rules.

`DEC-WARROOM-READINESS-001`: Board responses reuse request-scoped facts. Missing
cached evidence remains unknown; polling does not discover providers, perform
expensive per-feature Git probes, dispatch, or mutate lifecycle state. Action
boundaries re-evaluate their gates. This preserves truthful explanations without
turning browser refreshes into execution or repeated discovery.

`REQ-WARROOM-ATTENTION-001`: New-feature markers and collapsed-epic counts remain
separate from lifecycle and activation summaries. Viewing or rendering a feature
never acknowledges it. Workspace-shared **Mark seen** requires the request-scoped
human verifier, records actor/time, and does not approve, dispatch, edit plans or
clear blockers. Keyboard navigation, contrast and screen-reader labels support
both markers and actions.

`DEC-WARROOM-ATTENTION-001`: The UI consumes the canonical tracking-workspace
attention ledger through `feature_attention_routes.py`. A monotonic revision
prevents an older poll response from undoing an acknowledgement. Unavailable or
corrupt state remains visibly unavailable and disables acknowledgement; it never
silently resets the baseline. Ledger persistence belongs to
[`feature_attention.py`](../feature_attention.py), which shares state across
managed worktrees and split repositories using atomic writes and locking.
Completed, cancelled and retired children leave pending-attention aggregates
without deleting provenance; replay and plan edits do not recreate acknowledged
newness.

Verification: [readiness evidence](../../tests/war_room/test_feature_readiness_evidence.py),
[board readiness](../../tests/war_room/test_board_feature_readiness.py), and
[attention API/browser scenarios](../../tests/war_room/test_feature_attention_api.py)
cover missing/stale evidence, explicit acknowledgement, concurrent revisions,
refresh persistence and storage failure.

## Architecture review boundary

The War Room presents revision-pinned architecture resources and review state.
Publication, artifact ownership, destination, generation, ancestry and byte-digest
validation belong to the [workspace design](../workspace/DESIGN.md), specifically
[REQ-WORKSPACE-001](../workspace/DESIGN.md),
[REQ-WORKSPACE-002](../workspace/DESIGN.md) and
[DEC-WORKSPACE-001](../workspace/DESIGN.md). Registered owning
lineage determines each artifact's current revision; tracking and product
revisions remain distinct in split repositories. The UI does not grant permission
to publish or accept a stale review. Supported retries retain failure history and
exact proposal evidence.

The repository-owned [C4 model](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/model.dsl)
is authoritative; its [views](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/views.dsl)
represent the War Room, supervisor and repository boundaries. Readiness,
attention and audit presentation stay within these components.
[Architecture HTTP tests](../../tests/war_room/test_architecture_http.py) and
[tab UI tests](../../tests/war_room/test_architecture_tab_ui.py) verify the local
consumer boundary; [publication tests](../../tests/workspace/test_architecture_publication.py)
verify owner-lineage and exact-revision enforcement.
