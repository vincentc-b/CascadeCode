# Exact merge evidence closeout

This work record closes the implementation and architecture review for the
accepted-merge evidence contract. It does not create another receipt ledger or
move architecture ownership out of the package, Boss, Task, and Teams designs.

## Implementation evidence

- Forge snapshots expose a typed actual accepted identity containing the review
  URL and route, accepted source revision, actual merge SHA, and freshly observed
  target head. Missing merge identity remains unavailable.
- The review registry retains that actual identity and its local generation
  separately from the prospective candidate commit/tree and complete validation
  material.
- Teams binds a settled exact-candidate proof after leased publication. Review
  acceptance and Watchdog's later repair postcheck call the same Task-ledger
  receipt matcher used before publication. New generations clear prior proof.
- Route, source, original target, result, profile, runtime, fingerprint, operation,
  or generation drift refuses reuse. Duplicate callbacks read the existing
  receipt and do not create a review or validator operation.

## Focused verification

Commands were run from the Task worktree with Python 3.12:

```text
/opt/conda/bin/python3.12 -m pytest -q tests/test_tracking_find.py tests/feature/test_review_generations.py tests/task/test_incident_budget.py tests/test_review_rebase.py tests/test_review_publication_safeguards.py
```

Result: **94 passed in 60.27s**. This covers normalized actual identity, missing
merge SHA, generation/target drift, exact receipt A-B-A fencing, timeout and
candidate validation/publication safeguards.

```text
/opt/conda/bin/python3.12 -m pytest -q tests/test_late_repair_convergence.py tests/test_review_recovery_journey.py tests/workspace/test_c4_source.py
```

Result: **34 passed in 200.54s**. The real-repository journey covers the
incompatible Task boot contract, red-then-green repair, restart, exact review
reuse, forge acceptance and target convergence without live forge mutation.

```text
/opt/conda/bin/python3.12 -m pytest -q tests/workspace/test_c4_source.py tests/workspace/test_c4_render.py
```

Result: **21 passed in 61.96s**. The pinned Structurizr image validated and
rendered the authored closure; the second render exercised verified cache reuse.

`ruff check` on the changed Python/test paths and `git diff --check` also passed.

## Design and architecture reconciliation

Reviewed and updated `cascade/DESIGN.md`, `cascade/boss/DESIGN.md`, and
`cascade/task/DESIGN.md`. Workspace has no changed public materialization
interface, so `cascade/workspace/DESIGN.md` needs no edit. The implementation
adds no actor, external system, deployed runtime, persistent store, or network
path, so landscape, context, and container views remain current.

The pinned `model.dsl`, `views.dsl`, and `workspace.contract.json` were updated
together. `cascade-teams-code` owns proof binding and the existing exact receipt
matcher; `cascade-boss-code` owns acceptance/postcheck orchestration. Task retains
budget/admission ownership. Source-contract and real-render checks verified
declaration kinds, source paths/symbols, component parents, view inventory,
context-to-Code availability, Level-up metadata, deep-link keys, source-opening
metadata, stale-symbol refusal, warm artifact reuse, and configured render bounds.
No accepted snapshot was rewritten. There are no unresolved architecture gaps.
