# Branch architecture browser evidence

Task `task_046_005_002` ran the real War Room architecture context and snapshot
routes with the repository's pinned local Structurizr image and native Chromium.
The browser fixture starts the production `serve` entry point on loopback; it does
not inject review JSON, replace HTTP endpoints, or supply placeholder SVG.

## Reproduction

Prerequisites already authorized by the epic are the locally installed Docker
runtime, pinned image, Playwright Python package, and native Playwright Chromium.
No dependency was installed for this proof.

```text
CASCADE_BRANCH_BROWSER_EVIDENCE_DIR="$PWD/docs/task_artifacts/task_046_005_002" \
  pytest tests/war_room/test_architecture_browsing_browser_journey.py -q -rs
```

An initial proof-track run failed twice: the production renderer reached its
90-second total deadline during trusted binding, and the split fixture initially
wrote its design at the tracking root instead of the configured design
destination. The fixture path was corrected, the production render remained
bounded but gained a 180-second cold/contended-host allowance, and both scenarios
passed. The final integrated run executed this module together with the paired
review module: `3 passed in 375.66s`, with no skip. Cascade's supervised
`final_validation` is attached to the final deliverable commit.

## B1-B5 results

| Criterion | Result | Production-path evidence |
| --- | --- | --- |
| B1 default branch and pinned commit | Pass | Session target opened on real `main`; provenance and source resource both carried `2d9ffba135cbde10524672fed047faa43226ef99`. |
| B2 browsing and differing branch | Pass | View selection, semantic element/relationship selection, drill/back, fit/zoom/pan, source read, and board/tab switching ran before opening `feat/feat_branch` at `a3273191c275c283c633bb2eddf15b6736b817ce`, whose rendered system name was `Branch Atlas`. |
| B3 deep-link recovery and explicit refresh | Pass | Reload restored the snapshot/view/semantic-target URL. Advancing branch HEAD to `c6222b14a4fb3c4a828550fb3572ff9083868c3e` left the old SVG/source pinned until the visible refresh action created a new snapshot. |
| B4 detached, dirty, and missing | Pass | Detached provenance remained at `2d9ffba135cbde10524672fed047faa43226ef99`; dirty `DIRTY SECRET` bytes were excluded. Missing-model revision `f8bffacdd6004f66e1765beb23fc732b2dd1328b` and invalid-model revision `fa1e097f241117b3e83b305427b15054769d9380` produced explicit states without disabling the tab. |
| B5 split refs and absent association | Pass | Durable accepted lineage bound code `ec5b2b7846ecd47eda91290bec8b3df8bf39158d` to distinct documentation `94776fdddb6bb94c68cf94391961e6726ff6fe92`. After real code HEAD advanced to `eb2fb6f31fa261edc2689bd32bdd820305f054fb`, the fresh route refused to guess tracking HEAD and rendered only after opaque documentation ref `documentation-08633f912366f8435c280b5d835fd636` was explicitly selected. |

Exact snapshot, review, lineage, documentation-ref, renderer digest, resource
limits, and fixture revisions are retained in [colocated-revisions.json](colocated-revisions.json)
and [split-revisions.json](split-revisions.json).

## Screenshots

- [Differing branch browsing](branch-browsing.png)
- [Detached and dirty provenance](detached-dirty.png)
- [Missing model state](missing-model.png)
- [Exact split association](split-exact-association.png)
- [Absent split association](split-absent-association.png)
- [Explicit split documentation selection](split-explicit-selection.png)
