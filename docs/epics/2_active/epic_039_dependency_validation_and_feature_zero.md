---
id: epic_039
title: Dependency validation and feature zero
tier: epic
status: active
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-06'
updated: '2026-11-06'
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
# Dependency validation and feature zero

## Intent

Make external toolchain, runtime, service, and package prerequisites an explicit bootstrap phase before ordinary feature delivery. During epic planning, the team lists and validates required dependencies in the actual execution environment. Treat this bootstrap as a narrowly authorized "feature 0": agents may install pinned dependencies when policy and permissions allow; otherwise Cascade blocks safely and gives the human exact investigation, installation, and verification steps. After the human installs or resolves the dependency and pings the team, validation reruns and planning resumes without restarting the epic.

### Success criteria

1. Every epic plan records an explicit dependency manifest before ordinary feature minting. Each entry includes name, purpose, selected version/range, authoritative source, install scope, execution environment, license/security considerations, verification command, and evidence or an explicit "none required" result.
2. Cascade runs dependency checks in the same environment that will plan, build, test, or render the work. Host, container, worktree, remote runner, and agent sandbox differences are visible rather than inferred.
3. Bootstrap work is a first-class, board-visible pre-feature phase ("feature 0" semantics) with a narrow human-reviewed scope. It can perform feasibility checks and dependency setup needed to finish the full epic plan without preapproving ordinary implementation features.
4. Agents may install dependencies only when current policy permits the exact mutation. Prefer project-local, user-local, containerized, reversible, version-pinned installs with checksums/digests. Never silently use sudo, change system-wide defaults, add credentials, accept licenses, publish externally, or follow moving `latest` references.
5. If installation is not permitted or feasibility needs human judgment, the epic enters a visible dependency-blocked state. The human receives the failing check, why the dependency is required, exact safe install/investigation steps, expected verification output, cleanup/rollback guidance, and a clear "ping team after completion" action.
6. A human ping resumes the existing planning run, rechecks every blocked dependency, records immutable evidence, and proceeds only when checks pass. Repeated pings and installs are idempotent; accepted work and planning history are preserved.
7. Dependency evidence is revision-bound: selected versions, distribution hashes/image digests, transitive lock data where available, check outputs, and the manifest revision are attached to sign-off. Changes invalidate only affected authorization.
8. Detect circular planning gates. A feasibility adapter or tool needed to validate the main plan must be allowed inside the bootstrap scope, or the plan must surface an explicit human decision; it must not require an unmintable ordinary feature to satisfy pre-mint sign-off.
9. War Room shows dependency status, responsible actor (agent or human), last check, actionable failure, and resume control. Agent chat summarizes live state from the manifest/check result rather than stale prose.
10. Tests cover successful agent-local/container installation, denied system installation, offline/unavailable sources, checksum mismatch, license/credential prompts, human install plus ping/resume, environment mismatch, partial setup recovery, and a no-dependency epic.
11. Apply the workflow to epic_034's Structurizr prerequisite as an acceptance scenario: identify the host Java mismatch, allow a pinned containerized distribution, record its immutable digest and bundled runtime, and keep adapter feasibility distinct from dependency installation.

## Macro-architecture

### Scope and delivery boundary

Deliver one dependency-validation workflow integrated with existing epic planning. "Feature 0" is an epic-owned bootstrap record and execution phase, not an ordinary numbered feature, a new work-item tier, or permission to bypass the existing sandbox. No general package manager, arbitrary remote execution service, automatic fleet provisioning, vulnerability scanner, credential manager, or Structurizr product adapter is included. Existing approved work is preserved.

### Canonical records and execution

1. The epic owns a versioned dependency manifest, including an explicit empty manifest when no prerequisites are required. Each entry has a stable dependency ID, purpose, selected range and resolved exact version, authoritative distribution source, artifact checksum/image digest where applicable, install scope, target environment identity, license/security notes, verification command and expected result, and evidence references. Record unavailable hashes or transitive lock data explicitly; never invent them. A new install requires an exact version and integrity information.
2. A bootstrap scope records the manifest revision, allowed dependency IDs, exact setup/check operations and destinations, permitted feasibility artifacts, runtime/resource limits, cleanup steps, and human authorization provenance. Human review authorizes only this scope; current execution policy can still deny it. Read-only discovery may precede authorization; all setup and feasibility mutations require it.
3. Checks execute through a bounded runner in the declared environment. Evidence includes attempt ID, timestamps, environment fingerprint (runner, repository/worktree, sandbox, executable/runtime, and container digest as applicable), exact operation, exit status, redacted output, selected versions and integrity/lock references, and manifest/scope revisions. Store attempts append-only in the owning tracking repository; projections are derived from these records. Do not treat a host check as a sandbox, container, or remote-runner check.
4. Separate dependency readiness from adapter feasibility. A tool can be installed and valid while an adapter proof remains blocked. A minimal feasibility script or adapter belongs in the reviewed bootstrap scope only when needed to finish planning; it has bounded inputs, outputs, paths, and cleanup. A missing permission or unresolved feasibility choice produces a human action, not a dependency on an unmintable feature.
5. Use existing tracking-repository routing, planning sign-off/readiness, lifecycle serialization, provider recovery, and War Room action surfaces. Relevant current seams include `cascade/epic/planning_signoffs.py`, `plan_readiness.py`, `mint.py`, `lifecycle_gate.py`, `cascade/agent/planning_sandbox.py`, MCP wrappers, and War Room server/read models. Preserve existing access controls; feature teams choose exact record schemas and module placement within these contracts.

### Readiness, authorization, and recovery contract

- Bootstrap states are `unchecked`, `awaiting_authorization`, `checking`, `dependency_blocked`, and `ready`. The epic stays active while blocked; retain its run/checkpoint, accepted work, and history. Each blocker identifies dependency, environment, responsible actor, last attempt, failure, and next action.
- Before ordinary feature minting, planning sign-off, or plan approval, recompute readiness against the current manifest and required environment checks. Missing manifests, unknown environments, incomplete checks, unresolved feasibility, and stale evidence fail closed. An explicit validated empty manifest passes without setup or an unnecessary authorization prompt.
- Under lifecycle serialization, admit an attempt with a stable identity, perform the bounded operation outside a long-held lifecycle lock, then recheck revision and policy before accepting its result. Reject stale completions as current readiness while retaining their evidence. Do not launch concurrent installs for the same scope/environment.
- A human ping or the explicit resume action requests revalidation; it never certifies success or grants new installation authority. Recheck every blocked entry and any previously passed entry affected by environment or manifest change. Deduplicate repeated delivery and concurrent requests. After interruption, reconcile actual installed state before retrying; do not assume installation is either complete or rolled back. Bound retries and timeouts; persist actionable failure instead of spinning.
- Bind sign-off to the plan revision and an immutable dependency-evidence snapshot. A changed dependency, source, digest, environment, verification recipe, or bootstrap scope invalidates its evidence and dependent authorization only. Unrelated dependency approvals survive; a changed epic document still requires both existing role sign-offs on its new revision.
- For existing epics, enforce the manifest at their next guarded planning action; do not fabricate an empty manifest, cancel accepted work, or restart their runs. Preserve software prerequisites separately from work-item `depends_on`.

### Human handoff

For each blocker, show why the dependency is necessary, the exact failed command and environment, observed output, required investigation or pinned installation steps, expected verification result, and cleanup/rollback instructions limited to owned artifacts. When facts are unknown, request the exact investigation needed rather than inventing a safe install command. Show a "Ping team after completion" action. License acceptance, credentials, privileged/system changes, unavailable execution environments, and unsupported setup methods remain explicit human actions.

### Validation strategy

Use a small set of integration/API lifecycle tests with a deterministic runner for denial, offline sources, integrity mismatch, prompts, environment mismatch, interruption, stale revisions, duplicate pings, and recovery. Assert actual authorization boundaries, durable evidence, preserved history, and readiness transitions rather than duplicating implementation-level unit tests. Include a harmless real project-local installation and a pinned container smoke check in an authorized execution environment; simulated runs alone do not establish installation support. Reuse existing War Room browser/API tests for the visible blocked/resume flow and no-dependency flow.

The Structurizr acceptance scenario must record the actual incompatible host Java result, the selected pinned distribution/container digest and bundled Java runtime, and a successful check inside that container. Separately exercise adapter feasibility and its bootstrap authorization. Do not require installing host Java or shipping epic_034's adapter. If the real smoke environment is unavailable, record a blocker and do not claim the scenario passed.

## Cross-module constraints

Build on existing planning sign-offs, lifecycle locks, provider recovery patterns, and War Room action/retry surfaces. Installation authority must be explicit and least-privilege. Do not turn dependency setup into unrestricted shell access. Keep software dependency validation distinct from work-item `depends_on`, while presenting both coherently to humans.

## Core dependencies

### epic_039 planning manifest — revision 1, 2026-11-06

No additional external dependency is required to finish this epic's design or to implement its records, gates, and UI using the existing stack. This is not a claim that future build/test or Structurizr environments have passed validation.

Observed planning environment: read-only scratch directory `/tmp/cascade_planning_5p78acx1`; repository worktree `/home/ubuntu/dev/CascadeCode/.cascade/worktrees/epic_epic_039` is a distinct context; Python executable `/opt/conda/bin/python`; Linux x86_64, kernel `6.8.0-1021-aws`, glibc 2.35. Installation is not authorized in this session. Evidence below is command output observed on 2026-11-06 in this planning process, not a future runner attestation.

| Dependency / purpose | Selection and observed result | Source, scope, verification |
| --- | --- | --- |
| Python, existing application/test runtime | Repository requires >=3.12; observed 3.12.8 | Worktree `pyproject.toml`; existing process environment; `python --version` |
| PyYAML, board documents | >=6; observed 6.0.3 | Worktree `pyproject.toml`; existing Python environment; package metadata check below |
| cursor-sdk, existing provider integration | >=0.1; observed 1.0.37 | Same declaration, scope, and metadata check |
| langgraph, existing orchestration | >=0.2; observed 1.2.14 | Same declaration, scope, and metadata check |
| langgraph-checkpoint-sqlite, durable checkpoints | >=2; observed 3.1.1 | Same declaration, scope, and metadata check |
| setuptools, existing build backend | >=68; observed 80.9.0 | Same declaration, scope, and metadata check |
| pytest, lifecycle tests | >=8; observed 9.0.3 | Worktree `pyproject.toml` dev extra; existing Python environment; metadata check |
| Git, existing repository lifecycle | Existing installation observed 2.34.1; no new version constraint introduced | Installed executable; `git --version` |
| Node, existing War Room JavaScript test harness | Existing installation observed 20.20.2; no new version constraint introduced | Installed executable; `node --version` |

Metadata verification: `python -c 'import importlib.metadata as m; print({n:m.version(n) for n in ["PyYAML","cursor-sdk","langgraph","langgraph-checkpoint-sqlite","setuptools","pytest"]})'`. All declared package versions were found; this proves availability, not application behavior.

For all existing entries: install scope is unchanged and no install is requested; authoritative project requirements are the checked-in declaration, while observed versions come from local executables/package metadata. No new license acceptance, credentials, or security exception is requested. Distribution authenticity, license review, transitive lock data, and hashes were not established by these availability checks and must not be reported as verified. Any future setup must supply authoritative upstream provenance and the exact policy-permitted pinned recipe.

Delivery-only acceptance prerequisite: an authorized environment for local setup and a container runner with a pinned Structurizr distribution. Selection, upstream provenance, digest, bundled runtime, license/security notes, exact check, cleanup, and real evidence belong to feature B before that acceptance scenario can pass. They are not prerequisites for designing this workflow. The epic_034 description in the approved brief is the acceptance input; this turn did not inspect or change that epic.

## Feature breakdown

Three sequential features are the smallest delivery slices; no ordinary feature is itself the bootstrap phase.

| Slice | Scope and exit criteria | Prerequisite | Brief criteria |
| --- | --- | --- | --- |
| A — Dependency manifest, evidence, and planning gates | Durable revisioned manifests, environment-specific append-only attempts and evidence snapshots; scoped invalidation; authoritative guards on mint/sign-off/approval; explicit empty-manifest and legacy behavior. Integration tests prove missing/stale data blocks and valid data passes. | None | 1, 2, 7; foundations for 8–9 |
| B — Authorized bootstrap and resumable dependency checks | Epic-owned bootstrap record, human scope authorization, bounded policy-enforced checks/setup and feasibility; durable blocked guidance, idempotent ping/resume and partial recovery. Prove local/container setup and all denial/failure cases; record actual Structurizr container/runtime evidence separately from feasibility. | A | 3–6, 8, 10–11 |
| C — War Room dependency controls and acceptance flow | Shared status projection for UI and agent chat; responsible actor, last check, actionable instructions, human bootstrap review and resume controls. Exercise full block → human action → ping → recheck → planning flow, stale authorization, restart/duplicate delivery, and no-dependency flow. | B | 9–11 and end-to-end 1–8 |

Feature plans must retain these acceptance obligations. Feature teams may resolve implementation details without adding a package-management framework or widening installation authority. Ordinary implementation dispatch remains subject to existing plan approval.

## Open questions

None at epic contract level. The formerly open risk question is resolved by the bootstrap boundary, revision/environment evidence contract, guarded action semantics, and recovery rules above. Concrete record schemas and bounded-runner details belong to feature planning. Real installation and Structurizr evidence remain delivery acceptance obligations, not unverified planning claims.

## Decision log

- 2026-11-06 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-06 · Epic Manager · **Macro-architecture**
  Chose Represent feature 0 as an epic-owned, human-scoped bootstrap phase, with dependency readiness separate from adapter feasibility; no new ordinary feature tier or general package manager..
  Rationale: Break the pre-mint feasibility cycle while keeping setup authority bounded by both human scope and current execution policy.
  Honors: Success criteria 3, 4, 8 and the approved cross-module constraints..

- `dec_002` · 2026-11-06 · Epic Manager · **Macro-architecture**
  Chose Gate minting, sign-off, and approval on current environment-specific evidence; preserve active runs and accepted work across idempotent human ping/revalidation; invalidate only affected dependency authority..
  Rationale: A human ping is a request to verify, not proof of success. Durable attempts and revision checks prevent stale or duplicated setup from authorizing delivery.
  Honors: Success criteria 1, 2, 5, 6, 7, 9..
## Amendment log

_(none)_
