---
id: feat_018_003
title: 'Update failure containment: preflight, bounded backoff, degraded responder, and health status'
tier: feature
status: backlog
parent: epic_018
children: []
depends_on:
- feat_018_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-23'
updated: '2026-10-23'
provider: cursor
models:
  feature_lead: claude-opus-5-5
  feature_architect: claude-opus-5-5
approved_at: '2026-10-23T02:49:27.969137+00:00'
---
# Update failure containment: preflight, bounded backoff, degraded responder, and health status

## Parent Epic

epic_018

## Scope

## Intent

Make a bad update visible and survivable rather than silent downtime.

## Builds on feat_018_001 (completed)

Per the epic's "Handoff seams from feat_018_001" (dec_009, dec_010), this feature extends 001's seams instead of rewriting its launcher loop:

- The preflight goes **in front of** 001's single worker shutdown entry point, for reason `update` only. feat_018_002 adds the drain inside that entry point in parallel; do not move or duplicate it.
- 001's fixed ~1s crash-relaunch delay is replaced by the backoff below.
- 001's single launcher state-transition function gains the `supervisor_status.json` write.
- Backoff and the 60s counter reset key off 001's readiness signal, which means "serving on the inherited fd" (sent before resume).
- The degraded responder detects the next source change with 001's stdlib-only fingerprint function, already imported by the launcher at start; it must not import changing Cascade modules.
- The trunk `index.lock` warning comes from the data 001's sweep returns.
- Before building, confirm these seams against the merged 001 code. If one is missing or shaped differently, raise an upward question rather than reworking 001 inside this feature.

## Acceptance

- **Preflight:** before draining for a source update, the running worker launches a short-lived subprocess that imports the Cascade entry modules from the new source and runs `prepare_up`. If it fails, the old worker keeps serving, status shows `update_blocked` with the error output, and it retries on the next fingerprint change. Operator stop skips preflight.
- **Backoff:** if a new worker exits before reporting ready, the launcher retries with exponential backoff (1s doubling, capped at 30s, at most 5 consecutive attempts; the counter resets after a worker stays ready for 60s).
- **Degraded mode:** after attempts are exhausted the launcher stays alive holding the lock and socket, answers every request itself with `503` and a JSON/HTML diagnostic (last exit code, stderr tail, next action), and launches again automatically on the next source fingerprint change or on SIGHUP.
- **Status:** the launcher writes `.cascade/supervisor_status.json` (`state` serving|draining|restarting|update_blocked|degraded, worker pid, restart count, last error, timestamps, and any product-trunk `.git/index.lock` warning from feature 1's sweep). `GET /api/health` returns it from both the worker and the degraded responder, and the War Room shows a banner whenever state is not `serving` or a trunk lock warning is present. Every transition is logged on stderr with one line.
- Integration tests: (a) a syntax error introduced into the source triggers `update_blocked` and the old worker keeps answering; (b) a worker that crashes on startup produces bounded retries, then degraded 503 with diagnostics; fixing the source recovers to `serving` without an operator.

## Out of scope

HTTP and turn drain, replay-safe board tools and atomic writes (feature 2).

## Data structures

TBD.

## API contracts

TBD.

## Logic flow

```mermaid
flowchart TD
  A[Start] --> B[End]
```

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

- feat_018_002 works in the same worker shutdown entry point in parallel. Keep the preflight in front of it and the drain inside it so the two merge without conflict.

## Decision log

None yet.
