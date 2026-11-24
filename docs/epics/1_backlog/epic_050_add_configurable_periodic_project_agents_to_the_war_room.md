---
id: epic_050
title: Add configurable periodic project agents to the War Room
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
created: '2026-11-24'
updated: '2026-11-24'
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
# Add configurable periodic project agents to the War Room

## Intent

Give each Cascade Code project recurring agents for maintenance that otherwise depends on someone remembering to ask. An operator can schedule a documentation, architecture diagram, or performance audit by calendar or by completed epic delivery, and can run it on demand. Each agent follows a versioned project skill that says what to check, what evidence to collect, and what to produce. The War Room makes the definition, skill, next trigger, and results inspectable.

Cascade's existing periodic health audit checks the health of Cascade's own delivery lifecycle. This epic adds operator-authored project maintenance with its own schedules and publication authority.

### Success criteria

1. **Project configuration.** Define multiple opt-in agents in the project's `cascade.yaml` or `cascade.yml`, with equivalent support for existing `cascade.toml` projects and a single source of truth. Each definition has a stable ID, display name, automatic scheduling switch, skill reference, one trigger, and explicit output permissions. Reuse project config discovery and provider/model defaults and validation. Missing or invalid values, unresolved skill paths, and unavailable providers produce actionable status for the affected definitions. Workspaces with no definitions keep their current behavior.
2. **Calendar trigger.** Support recurring wall-clock schedules such as Mondays at 09:00 in a named time zone. Show the effective time zone and next occurrence before saving. Document and test daylight-saving behavior, with one run for a repeated local time and skipped nonexistent local times. After downtime, coalesce missed slots into at most one due run. A manual start can satisfy calendar slots already due and leaves future calendar slots at their configured times.
3. **Epic-merge trigger.** For every Nth epic, count each distinct, verified implementation delivery onto the configured product trunk once. Use existing epic delivery evidence for forge merges, including squash merges, and for supported local promotions. Handle split product/tracking repositories. Brief merges, feature or task merges, metadata-only closeout reviews, and ordinary direct changes do not count. Start from the effective definition's baseline. Reconcile duplicate, late, or out-of-order observations and surface unavailable evidence. Show progress such as **3 of 5 epics merged** and why the scheduler is waiting.
4. **Manual runs and schedule accounting.** Authenticate the operator's Run now request and admit it through the same durable supervisor path as scheduled work. Show the schedule impact before submitting. When a manual run durably starts at 3 of 5, the counter becomes 0. Five more qualifying merges are then required for the next automatic run. Merges after the recorded start boundary count toward that next run, including merges during execution and evidence discovered later. A refused request, a request that never starts, or a duplicate click does not reset progress. If a manual request overlaps a pending scheduled trigger, coalesce it into one start and one accounting update. An already running attempt is shown and linked without a second reset. Retries of a started run retain its original boundary and output identity. Record start and trigger consumption together so a restart preserves both. A scheduled epic-count run also establishes a fresh baseline when it starts, including after a backlog of eligible merges.
5. **Supervisor operation.** Preserve definitions and run history across restart and worktree cleanup. Admit one in-flight run per definition with bounded project concurrency, provider use, execution time, and retries. Keep normal delivery responsive. Coalesce overdue work and handle abandoned claims without duplicate execution or publication. Automatic scheduling can be paused while authenticated manual runs stay available for valid definitions. Track eligible merges while paused and coalesce any overdue automatic work on resume. Pin each run to the admitted definition, skill revision, and product snapshot. Preserve history and progress on display-name or skill edits. Show the new baseline when a reviewed trigger change takes effect.
6. **War Room creation and editing.** Add a **Periodic agents** area with a **New periodic task** action. A menu lets the operator pick the trigger method, configure frequency, and preview the next run or merge target. Open a scoped authoring session in the existing agent/chat experience to draft a skill from the template or revise an existing one. Let the operator inspect and edit the skill Markdown, review configuration and skill diffs together, then submit a normal review. Use a stale-safe review path that preserves hand-edited configuration and current worktrees. Show draft and pending-review definitions without scheduling them. Load executable definitions and skills from the effective committed project revision, and apply UI-authored changes when their review lands. Support edits, pause/resume, and removal with history still available.
7. **Skill template.** Install a reusable in-repository `SKILL.md` template for periodic agents. Prompt the author to specify the objective, repositories and paths in scope, inspection steps, validation commands and evidence, thresholds and severity, expected result format, and when to publish or escalate. Include how to report no findings, repeated findings, insufficient evidence, and failures. Show examples for checking docs against current behavior, diagrams against the product revision, and performance against a reproducible benchmark. Make the effective skill and its version inspectable from the agent and each historical run.
8. **Results and publication.** Default to a read-only audit that records findings in the run. An operator may explicitly enable filing a normal War Room backlog brief for larger findings, opening a scoped change MR for small verified fixes, or both. Require evidence, validation, and links to the run, audited revision, and related open work. Define when the agent should link to or update an existing finding. Enforce publication rights outside the skill text, with explicit repository and path scope. Keep permission expansion reviewable in the configuration diff. The agent may open an authorized review and report its outcome. Human approval and the destination repository's usual review gates still govern merges, brief activation, and follow-up work. The agent cannot grant itself permissions, edit its own schedule or skill, or mutate protected branches.
9. **War Room operation.** Show definitions created in either config or UI, their effective schedule and skill, enabled/paused state, next due time or merge progress, and any blocker. Provide **Run now** with queued, running, blocked, failed, and completed outcomes. Show a bounded run history with trigger source, timestamps, audited revision, safe findings summary, and links to the relevant session, brief, or change MR. Distinguish a clean result from an incomplete audit or a publication failure. Refreshing the dashboard reads persisted status without dispatching or driving reconciliation.
10. **Integrated acceptance.** Exercise both triggers and both authoring paths from normal product entry points. Verify a manual reset at 3 of 5, four later merges with no dispatch, and one automatic start on the fifth. Also cover threshold races, restart and late evidence, merges during runs, paused and edited definitions, calendar downtime and time-zone transitions, split repositories, unavailable providers, invalid skills, and an interrupted publication retried without creating a duplicate review. Prove the report-only, brief, and change-MR paths with controlled fixtures and verify that drafts cannot run and unauthorized runs cannot publish.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use the supervisor's existing scheduling, claim, provider, and recovery boundaries where applicable. Preserve the existing health audit's cadence, manual-run behavior, and repair authority from epic_013, along with epic_044's health-audit presentation. Use the canonical epic implementation review and product-trunk evidence described by epic_028 and the product/tracking routing introduced by epic_036. Use the architecture destination and revision-aware browsing from epic_046 for diagram evidence where relevant.

Run audit and authoring agents in isolated, capability-scoped workspaces. Use repository-bound skill paths and existing review, validation, and human-authentication controls. Keep operational receipts outside watched board and queue inputs. Keep reads bounded and avoid exposing credentials, private reasoning, or raw subprocess output. Apply the correct product and tracking repository destinations to changes and findings, and preserve unrelated operator work.

The initial scope is calendar and epic-merge triggers with one trigger per definition. General event automation, external scheduling services, and autonomous approval or merging are outside this epic. The Epic Team should confirm the exact calendar syntax, canonical merge ordering, and config reload boundary during planning.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-24 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
