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

The two scenarios were also rerun separately while repairing the observed cold
renderer timeout:

```text
...::test_split_repository_requires_and_applies_an_explicit_documentation_ref
1 passed in 45.92s

...::test_branch_architecture_is_pinned_navigable_and_refreshes_whole_snapshot
1 passed in 170.73s
```

An initial run failed twice: the production renderer reached its 90-second total
deadline during trusted binding, and the new split fixture initially wrote its
design at the tracking root instead of the configured design destination. The
fixture path was corrected, the production render remained bounded but gained a
180-second cold/contended-host allowance, and both exact failing scenarios passed
on rerun. The final supervised command/result is recorded by Cascade's
`final_validation` attached to the deliverable commit.

## B1-B5 results

| Criterion | Result | Production-path evidence |
| --- | --- | --- |
| B1 default branch and pinned commit | Pass | Session target opened on real `main`; provenance and source resource both carried `acf8760da40dc572594a614b5e8933208e63196a`. |
| B2 browsing and differing branch | Pass | View selection, semantic element/relationship selection, drill/back, fit/zoom/pan, source read, and board/tab switching ran before opening `feat/feat_branch` at `f562ebc5be3ba4ba7177b77ff74e1be70367abf6`, whose rendered system name was `Branch Atlas`. |
| B3 deep-link recovery and explicit refresh | Pass | Reload restored the snapshot/view/semantic-target URL. Advancing branch HEAD to `4a0708ad9bbbbc6c3b66a13b81132f191438cf13` left the old SVG/source pinned until the visible refresh action created a new snapshot. |
| B4 detached, dirty, and missing | Pass | Detached provenance remained at `acf8760da40dc572594a614b5e8933208e63196a`; dirty `DIRTY SECRET` bytes were excluded. Missing-model revision `c03dbcc0ac139ee556d57af2eaba5e297de7f2b1` and invalid-model revision `538b9c2effaebbe7c8be42e71b106cb0525b33ea` produced explicit states without disabling the tab. |
| B5 split refs and absent association | Pass | Durable accepted lineage bound code `f9530cf618fe1f8068c1dbb11c0a532a7023f9ca` to distinct documentation `820f235add288bfab262f306291c29070f92edab`. After real code HEAD advanced to `76f04983bed375259e1bd6ef28929b0a80dc7890`, the fresh route refused to guess tracking HEAD and rendered only after the recorded opaque documentation ref was explicitly selected. |

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
