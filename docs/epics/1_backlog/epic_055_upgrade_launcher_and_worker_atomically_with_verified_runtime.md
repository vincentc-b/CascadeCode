---
id: epic_055
title: Upgrade launcher and worker atomically with verified runtime readiness
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Upgrade launcher and worker atomically with verified runtime readiness

## Intent

Make Cascade's own software update a coordinated, observable supervisor lifecycle transition. Epic 048 added reviewed installed/loaded runtime identity and changed the worker readiness handshake from a plain readiness signal to a structured receipt. The existing long-running launcher continued running its old code after main changed, spawned the new worker repeatedly, rejected the new readiness message, and exhausted five startup attempts. The War Room returned HTTP 503 even though the merged board and source checkout were healthy. The operator had to gracefully restart the entire launcher, not just the worker, after synchronization; health and board recovered. Preserve the independent runtime identity and signed deployment authority contracts from Epic 048 while making protocol-changing upgrades and ordinary source updates coherent, bounded and independently verified instead of requiring manual detection/restart.

### Success criteria

1. Define an explicit versioned compatibility contract for launcher/worker startup, health/readiness and any inherited sockets/authority manifest. Before activating new worker code, verify that the live launcher and candidate worker share a supported protocol and compatible runtime generation. An unknown or unsupported version produces a concise typed prerequisite instead of repeated parsing errors or false ready. Retain support for ordinary unverified local startup distinct from independently verified authorized recovery.
2. Provide an authorized, coordinated launcher-and-worker upgrade path for editable source and installed package updates. Bind the intended reviewed/integrated artifact and exact installed source/environment to the transition, preflight syntax/imports/dependencies and protocol compatibility, stop admitting work, gracefully drain active owners within the existing bounds, and reload both components when required. Preserve the workspace root, listen address/port, approved configuration, durable queue/checkpoints/claims, review and incident state. A worker-only update is allowed only when compatibility is positively established. Do not assert loaded provenance from mutable HEAD or a new PID alone.
3. Use durable lifecycle receipts for candidate preparation, drain, activation, readiness and independently verified completion, with replay-safe restart and one owner. Retain the last known working compatible runtime/launch recipe where an authorized reversible upgrade permits it. If preflight or readiness fails, stop bounded retries on unchanged evidence, keep/recover the last known healthy serving generation when safe, or expose an exact authority/rollback prerequisite. Never automatically install or roll back unreviewed code, silently change credentials/source trees or bypass an independent installation gate.
4. Keep health and War Room state truthful throughout update: report current versus candidate launcher and worker versions/revisions, compatibility, PID/start, capability generation, drain/activation stage, expected temporary outage and next safe step. A readiness receipt must remain bound to the actual live process, trusted source and runtime authority when required, using Epic 048's independent inspection; old-generation receipts, mixed source, wrong roots, unknown or stale manifests stay unverified. Do not expose secrets or raw large receipt payloads in errors. API/UI reads must be nonmutating and bounded.
5. Acceptance: reproduce the observed old-launcher/new-worker readiness mismatch with real local launcher and worker processes and isolated Git checkouts, using actual supported startup/upgrade interfaces. Demonstrate a compatible worker-only reload and a protocol-changing coordinated upgrade, graceful drain and replay, independent exact runtime postcheck, and recovery from failed candidate startup within a finite retry budget. Test restart interruption, concurrent upgrade requests, stale/invalid authority receipts, dirty source, same-port ownership, failed import/readiness, unsupported protocol, missing rollback authority, split target/tracking roots and ordinary local startup. Verify no lost or duplicated Task/review/incident ownership, no unintended product changes, consistent health/board after success and no repeated unchanged restart loop. Test actual process termination and readiness, not mocked successful returns.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Build on cascade/workspace/launcher.py, worker.py, source_fingerprint.py, supervisor_readiness.py, supervisor_status.py, runtime_identity.py, up.py, CLI, existing drain/lock/incident budget, and current reviewed runtime-bootstrap and independent postcheck contracts. Coordinate with Epic 048 (runtime authority and verified recovery), Epic 049 (progress visibility), and Epic 054 (trunk convergence). This brief owns compatible activation and process-generation convergence, not new deployment authority, installation credential issuance, a second supervisor/ledger or a general product deployment service. Preserve exact accepted revision checks and operator decision boundaries. Filing the brief does not authorize live installation or deployment; use normal planning and approval. Update the owning designs and affected C4 views when implementation changes.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-25 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
