# Integrated health-audit verification

This record covers the local producer, loopback API, and browser evidence at the
same checkout. It is not evidence from an approved deployment; post-deployment
live acceptance remains a separate closeout gate.

## Focused evidence

- `test_audit_integrated_experience.py` publishes real retained recovery sources,
  then reads them through a locally running War Room. The fixture retains two old
  failure generations, an initially timed-out candidate, a later verified blocker,
  malformed neighboring data, unverifiable legacy remediation reported as fixed,
  and completed work with outstanding publication. A second producer epoch models
  worker restart while preserving the first epoch's pending evidence.
- The same fixture configures distinct product and tracking roots, reads the
  tracking-owned follow-up snapshot from the product endpoint, issues eight
  concurrent status GETs, and compares every runtime input byte and modification
  time before and after. Lifecycle observation and provider probes are patched to
  fail if invoked.
- `test_health_audit_routes.py` exercises authenticated manual admission and
  coalescing with the real lane. `test_audit_lane.py` exercises receipt restoration
  and timed-out-candidate retention across lane reconstruction.
- `audit_status_ui_cases.mjs` exercises current, grouped coverage, legacy history,
  filtering, pagination, epoch restart, and stale-response suppression.
  `war_room_refresh_races.mjs` exercises three visible refreshes, five-second
  single-flight behavior, and asserts every refresh remains a GET of status rather
  than repair admission.

Focused command:

`pytest -q tests/war_room/test_audit_integrated_experience.py tests/war_room/test_health_audit_routes.py tests/war_room/test_audit_projection_reader.py tests/war_room/test_audit_status_ui.py tests/war_room/test_ui_render.py tests/watchdog/test_audit_projection.py tests/watchdog/test_audit_lane.py tests/watchdog/test_audit_producer_benchmark.py`

Pre-commit result: **94 passed** in 36.51 seconds.

## Representative 10,000-attempt measurements

Captured 2026-11-14 on CPython 3.12.8,
Linux 6.8.0-1021-aws x86_64 with glibc 2.35.

| Path | Measurement | Actual work / bytes |
| --- | --- | --- |
| Warm loopback HTTP GET | p95 38.543 ms over 30 samples; median 24.946 ms | 10,000 attempts in 100 incident rows; 922,913 source bytes; 76,178 response bytes |
| Projection producer | 0.356 s elapsed | 10,000 attempts, 100 generations, 20 malformed neighbors; 853,013 source bytes; 3 pages and 127,754 serialized page bytes |

The GET transport used loopback HTTP/1.1 with one request per connection. These
are warm local filesystem measurements, not cross-platform latency guarantees.
The feature defines structural ceilings but no portable latency target, so no
latency target is unmet or silently claimed. Candidate work remains bounded to
100 candidates, 60 seconds per pass, and two seconds per candidate; consumer
source and response ceilings are enforced separately by focused tests.

## Local smoke and limitation

The GET benchmark started the production War Room server on an ephemeral
loopback port, completed one warm-up plus 30 status requests, and shut it down
cleanly. The focused HTTP/UI tests also load the local UI and audit routes. This
local smoke does not establish normal post-deployment live acceptance.
