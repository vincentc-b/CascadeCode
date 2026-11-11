# task_046_005_004 — final A–D acceptance and operator guide

## Verdict

**Pass.** The final integrated production code at
`64779ff6773761244d6bfc72672c9e2ec363732b` passed the real renderer/native
Chromium paired-review and branch-browsing journeys with no skip. The only
subsequent worktree changes are this receipt and regenerated evidence. The
post-commit supervised result is attached to the deliverable as Cascade
`final_validation`; any later source or evidence edit invalidates that result.

No dependency was installed. The proof used the already-authorized local
runtime and image. A skipped renderer or browser check is a failed release gate,
even if the focused suites remain green.

## Reproducible operator procedure

Prerequisites:

- Docker is available to the operator.
- Local image
  `structurizr/structurizr@sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`
  is present. Its observed local image ID was
  `sha256:97681b22557abb2044ff2b67ae374956824c01da46b76be60858281adf678864`.
- Playwright Python support and native Chromium are present. The acceptance run
  recorded Chromium `156.0.8078.4`.
- Run from the repository root without installing or upgrading anything.

Launch the normal War Room for an operator session:

```console
cascade up
```

Open a feature plan from the board to review the paired current/proposed model.
Use **Architecture** to browse a known branch snapshot. A branch HEAD update does
not silently replace pinned content: use the visible refresh action. For a split
repository, select a recorded documentation ref when no exact association is
available; the UI intentionally does not guess tracking HEAD. Pending, failed,
missing-model, detached, and dirty states are explicit. Dirty bytes are never
included in a committed snapshot.

Reproduce the durable browser evidence:

```console
CASCADE_ACCEPTANCE_ARTIFACT_DIR="$PWD/docs/task_artifacts/task_046_005_001" \
CASCADE_BRANCH_BROWSER_EVIDENCE_DIR="$PWD/docs/task_artifacts/task_046_005_002" \
  pytest -q -rs \
  tests/war_room/test_architecture_planning_browser_journey.py \
  tests/war_room/test_architecture_browsing_browser_journey.py
```

Integrated result: `3 passed in 375.66s`; zero skips.

The pinned renderer settings recorded by every manifest are: timeout `180.0`
seconds, memory `1536m`, CPUs `2`, PID limit `256`, tmpfs `512m`, with network
disabled by the production renderer command and a fresh fixture-local
`.cascade/c4-render-cache`.

## A — paired review

All A1–A10 obligations passed through the real `/plan/{feature_id}` route after
a server restart. The journey used supported Epic/Feature planning publication,
not injected review JSON, endpoint mocks, fabricated paired payloads, or
placeholder SVG.

- Both nonempty SVGs were independently revision checked. Counterpart and
  added/removed element/relationship selection, diff styling, changed views,
  drill/back, native hit/fit/zoom, keyboard selection, desktop/narrow layout,
  and source/model/plan/design reads and diffs passed.
- Requirement and decision content opened on both sides; requirement, view,
  element, and relationship semantic roots all supported durable discussion.
- Local/incoming replies survived reload. Blocking approval, authorized
  resolve/reopen, stale-tuple rejection, removed-target outdated blocking, and
  final approval passed.
- Empty baseline, renderer recovery/cache reuse across restart, and an
  Epic-owned no-diagram-change proposal passed.

Runtime identities are in
[`task_046_005_001/evidence.json`](task_046_005_001/evidence.json). The final
Feature review unit is
`architecture-review-1a714e7262810e10a5d6be5ebd9c5c3199afb4b371079a6689f82a9879b64d32`
and its reviewed tuple digest is
`1a714e7262810e10a5d6be5ebd9c5c3199afb4b371079a6689f82a9879b64d32`.
The fixture baseline is `7459d46710b0a602c3e434ac4845b0cdaeadd371`,
the changed proposal is `801d8338dee662f5e5d8c56c8b68407f60ed6576`,
and final code, documentation, plan, and proposal ref are all
`edba55c944f028f8117c97551b021c15aeb21f25`.

Screenshots: [paired review](task_046_005_001/01-paired-review.png) and
[approved review](task_046_005_001/02-approved-review.png).

## B — branch architecture

All B1–B5 obligations passed through real context/snapshot routes: actual
default branch and pinned commit, differing branch, semantic browsing,
deep-link restoration, explicit whole-snapshot refresh after HEAD movement,
detached/dirty/missing/invalid states, and split code/document refs with exact
and absent association handling.

The colocated manifest records `main`/detached ref
`2d9ffba135cbde10524672fed047faa43226ef99`, branch ref
`a3273191c275c283c633bb2eddf15b6736b817ce`, refreshed ref
`c6222b14a4fb3c4a828550fb3572ff9083868c3e`, and review unit
`architecture-review-b0837f4a7c5bf0873ba9bb17fe1f711e3ab807bb34c5d8b6064b24e2795d09cb`.
The split manifest records accepted code
`ec5b2b7846ecd47eda91290bec8b3df8bf39158d`, documentation
`94776fdddb6bb94c68cf94391961e6726ff6fe92`, unassociated code
`eb2fb6f31fa261edc2689bd32bdd820305f054fb`, and review unit
`architecture-review-c3195a22d55fbb9a751801d3f3e3d8fceced5f3c0d6dfc07e1de644afa3d942a`.

Exact manifests and the six screenshots are indexed by
[`task_046_005_002/README.md`](task_046_005_002/README.md).

## C — focused failures and gates

The following scoped command passed `161` tests in `109.15s`:

```console
pytest -q \
  tests/war_room/test_architecture_http.py \
  tests/war_room/test_architecture_tab_ui.py \
  tests/war_room/test_paired_c4_review_ui.py \
  tests/workspace/test_architecture_authoring.py \
  tests/workspace/test_architecture_browsing.py \
  tests/workspace/test_architecture_context.py \
  tests/workspace/test_architecture_destination.py \
  tests/workspace/test_architecture_publication.py \
  tests/workspace/test_architecture_review.py \
  tests/workspace/test_architecture_snapshots.py \
  tests/workspace/test_c4_bindings.py \
  tests/workspace/test_c4_closure.py \
  tests/workspace/test_c4_diff.py \
  tests/workspace/test_c4_documentation.py \
  tests/workspace/test_c4_render.py \
  tests/workspace/test_c4_review.py \
  tests/workspace/test_c4_scheduler.py \
  tests/workspace/test_c4_source.py \
  tests/workspace/test_c4_threads.py
```

This covers first/empty baseline, justified no-change, legacy missing unit,
pending/failed renderer, invalid bindings, stale baseline, missing artifact,
stale comment, partial acceptance, and availability of unrelated plan/board
work. Desktop/narrow and native SVG interaction are additionally exercised by
the real browser journey rather than duplicated with mocks.

## D — evidence and integration fixes

The evidence directories contain eight nontrivial PNGs and three JSON manifests.
Every manifest was regenerated by the integrated run; `evidence.json` records
`"result": "pass"`.

Integration fixes retained from the proof tracks:

1. `f3e78930` kept rendering bounded while increasing the production total
   allowance from 90 to 180 seconds for the pinned multi-stage interactive
   pipeline. The initially timing-out branch scenario then passed.
2. `188d1ea8` made publication recovery reuse each proposal's pinned renderer
   settings instead of silently falling back to defaults. Its failure-gate and
   publication tests passed in the 161-test run.
3. `e7fe5cc6` corrected the split fixture's configured design destination and
   bounded its model to the views and semantics actually browsed. Both branch
   scenarios passed in the integrated browser run.
4. `98ef320d` consolidated the paired journey around normal planning tools and
   durable runtime-generated identities. That journey passed in the integrated
   browser run.

Observed failures are not hidden: the initial 90-second timeout and incorrect
split-fixture design path above failed during track development and were fixed
and rerun. The final integrated runs had no failures or skips.
