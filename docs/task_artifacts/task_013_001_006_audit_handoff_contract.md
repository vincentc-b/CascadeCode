# Audit foundation handoff contract

The scheduling and repair features should use the public functions below rather
than reading audit sidecars independently. The canonical implementation lives
under `cascade.watchdog`; this document records the stable handoff surface, not
a second lifecycle model.

## Scheduling handoff

- `audit.select_audit_candidates(cursor, budget, root=...)` returns a
  `CandidatePage`; its `.candidates` are typed `AuditCandidate` values and its
  `.next_cursor` is opaque. Callers persist the cursor outside canonical
  lifecycle state and must not decode it.
- `audit.project_audit_observation(work_id, root=...)` returns one immutable
  `AuditObservation`. Its classification is `healthy`, `expected_wait`,
  `proven_incident`, or `unavailable_evidence`.
- Candidate selection and observation are read-only. They do not sweep health,
  create lock files, rewrite sidecars, emit events, start model turns, or call a
  provider. An evidence parse or reachability failure is returned explicitly;
  it is never projected as healthy.
- The observation generation includes canonical document/Git/execution/gate
  evidence, direct-report revisions and execution state, and the
  capability-registry fingerprint. Only success for that exact generation may
  remain suppressed.
- Unresolved reconciliation actions are attributed through their durable review
  identity (`review_id` or `review_url`) to the typed owner in `reviews.json`;
  schedulers and repair adapters should not infer ownership from action keys.

## Repair handoff

- `incidents.project_incident(observation, ledger, failure_class=...)` decides
  whether the generation is eligible, cooling down, or permanently suppressed.
- `capabilities.probe_capability(incident, concrete_owner, root=...)` verifies
  the registered operation, exact owner authority, evidence/action/worktree
  reachability, finite retry policy, and durable result store. A missing probe
  remains an actionable incident with a resume action.
- `reservations.reserve_after_recheck(incident, capability, root=...)` performs
  the locked fresh recheck and returns `reserved`, `stale`, `gated`, or
  `unavailable`. A reservation is only an admission receipt; adapters release
  broad locks and repeat relevant publication preconditions before effects.
- `reservations.record_result(reservation, acknowledgement, result, root=...)`
  durably finishes the exact claim token. Replays are idempotent, expired claims
  can be reassessed, and prior generations and attempts remain in history.

Typed work identity is always `(tier, work_id)`. Document revisions, Git heads,
branches, action IDs, parent IDs, and incident generations remain separate
fields and cannot substitute for a work ID.
