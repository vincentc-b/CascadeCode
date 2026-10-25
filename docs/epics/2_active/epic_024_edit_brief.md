---
id: epic_024
title: Edit brief
tier: epic
status: active
parent: null
children:
- feat_024_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-luna
reasoning:
  epic_manager: high
  epic_architect: high
---
# Edit brief

## Intent

Give the human an Edit action on a backlog epic brief. They can change all brief-authoring fields, including agent assignments and reasoning, submit a new PR/MR for review, and see the merged revision on the same board item and plan view.

### Success criteria

1. Every eligible backlog epic brief exposes Edit. Opening it loads persisted content and assignments from the selected brief; it does not substitute new-brief defaults.
2. Editable fields include title, intent, success criteria, constraints, provider, and model/reasoning selections for all five existing roles: epic_manager, epic_architect, feature_lead, feature_architect, and swe. Other human-authored Markdown sections remain editable and round-trip without loss. “All fields” means brief-authoring content; ID, lifecycle, graph bookkeeping, approval history and runtime metadata remain system-managed.
3. A valid changed submission creates a new PR/MR against the configured product trunk and shows its link. The diff modifies only the existing brief, preserving its ID, path, creation metadata, untouched sections and unrelated metadata. Renaming the title does not allocate a new epic or rename the file.
4. Provider/model/reasoning validation follows the existing brief contract. Saved selections remain visible even when no longer available; validation must not silently change them. Reasoning overrides can be cleared explicitly. Cancel, no-op, and validation failure create no PR and leave approved content unchanged.
5. Submission checks the source brief revision and current backlog eligibility after fetching remote trunk. A changed, missing or activated target produces an actionable reload/conflict response instead of overwriting it. Unrelated trunk commits alone do not make an unchanged brief stale.
6. Before merge, the board continues to show approved content. After merge, the existing automatic sync cadence or forced refresh updates the same row and plan view, including title and agent selections, without duplicating the epic. This works for snapshot-only briefs and for briefs with stale local backlog copies.
7. Activation after refresh uses the approved revision displayed by the board. Local active/completed or live integration state remains authoritative, including when an edit PR merges after activation. Sync failure preserves the last valid view; refresh never resets, checks out, stashes or rebases operator or active worktrees.

## Macro-architecture

Deliver one vertical feature across the existing brief editor, Git-backed PR creation and backlog synchronization.

- **Editor and API:** Reuse the War Room brief dialog and provider/model/reasoning controls. Add an edit mode that retrieves the existing document plus source revision, submits changes for the selected epic, and retains form input on errors. Reuse the existing HTTP, validation and error conventions. Disable repeat submission while a request is in flight and distinguish PR creation from merge/board refresh.
- **Document update and review:** Extend the existing brief service and Git/forge helpers. Resolve the target by epic ID from the configured remote product trunk; use an isolated branch/worktree with a unique edit branch. Patch existing authoring content rather than rebuilding it with the creation template. Preserve non-edited Markdown/frontmatter. Verify the loaded document revision and lifecycle eligibility before committing; return a PR/MR link only when creation actually succeeds.
- **Merged content and activation:** Reuse the remote backlog snapshot and current polling/forced-refresh paths. Current snapshot import omits every local epic ID, merged-board precedence favors local copies, and activation source resolution prefers local HEAD. Narrowly extend these contracts so a validated merged revision of an eligible backlog brief is authoritative over a stale local backlog copy for board reads, plan reads and activation provenance. Preserve local/live lifecycle authority and diagnose genuine unmerged local-content conflicts rather than silently discarding them.

No new service, provider integration, polling loop, generic document editor framework or branch reconciliation system is required. Exact route names and editor presentation belong to feature design; the end-to-end contract above is fixed.

## Cross-module constraints

- PR review/merge remains the approval boundary for edited brief content; edit submission does not activate the epic or overwrite the approved local document.
- Backend eligibility checks are mandatory even when the UI hides Edit for non-backlog work. Recheck eligibility before creating the change. Existing forge review/conflict handling governs later trunk changes while a PR is open.
- Existing inventory validation and five-role semantics remain shared with creation. Never reset existing selections merely because defaults or inventory changed.
- Preserve stable epic identity, original document path, creation date, untouched Markdown and unrelated metadata. Do not reconstruct an existing brief from a blank template or silently drop unrecognized sections.
- Board rows, plan details, edit prefill and activation must agree on source content and provenance. Cache invalidation must allow a merged edit to become visible even when no new epic IDs were imported.
- Remote approved backlog may supersede only stale backlog content. Active/completed lifecycle state and live integration work are never replaced by remote backlog. Detect genuine local unpublished-content conflicts and retain the authoritative local view with diagnostics.
- Git/forge errors must be visible and leave entered values recoverable. If push succeeds but PR creation fails, identify the recoverable branch/state; do not claim a PR was created. General resumable PR management is outside scope.
- Preserve current configured remote/product-trunk resolution, polling behavior, authentication and human activation gate. No destructive operator-checkout operations.

## Core dependencies

- `cascade/briefs.py` and `cascade/brief_stack.py`: creation, persisted assignments and shared inventory validation.
- `cascade/war_room/server.py`, the existing brief dialog, `war_room.js` and `brief_defaults_ui.js`: edit affordance, prefill and submit flow.
- `cascade/tracking.py` and product-trunk resolution: isolated Git changes and supported forge PR/MR creation.
- `cascade/automation.py`, `cascade/workspace/backlog_snapshot.py`, `cascade/workspace/integration_worktree.py`, document routing and activation provenance: coherent approved content.
- Existing brief, API/UI and remote-backlog integration test fixtures. No new external dependency.

## Feature breakdown

1. **feat_024_001 — Edit backlog briefs through PRs and refresh approved content**
   - Deliver the Edit action, complete authoring-field prefill/editing, shared validation and conflict handling.
   - Create the isolated one-brief PR/MR while preserving document identity and content.
   - Make merged edits visible in board/plan reads and use that revision for activation.
   - Verify the full edit → PR diff → merge → refresh → activation-source path.

This is one shippable slice: an edit that creates a PR but leaves the board or activation stale does not meet the user intent. The feature team may sequence internal tasks; there are no sibling feature dependencies.

### Validation and delivery boundary

Prefer one integration scenario using real local Git repositories with the forge boundary faked: edit all authoring fields on a document containing extra Markdown, inspect the one-file diff, merge upstream, refresh, and verify the same board ID, plan content, assignments and activation source. Include stale local backlog and diverged operator checkout conditions. Add focused API/UI checks for prefill, clearing reasoning, invalid selections, no-op/cancel, stale revision, non-backlog rejection and submission failure recovery. Preserve create-brief regression coverage. Do not duplicate integration coverage with broad mock-heavy unit suites.

Out of scope: editing active/completed plans through this flow, automatic merging or activation, generic lifecycle/YAML editing, adding agent roles/providers, pending-PR dashboards, and general merge-conflict management.

## Open questions

No unresolved product-scope questions block feature planning. The feature design must settle the following implementation choices within this contract:

- Choose a lossless way to edit the supported Markdown sections and expose other author-authored sections; irregular documents must not be silently normalized or truncated.
- Define the source revision token and stale-local-versus-unpublished-local comparison. Cover snapshot-only and locally present backlog briefs consistently across reads and activation.
- Verify the eligibility/activation race and push-success/PR-failure recovery using existing infrastructure. A late merged edit must never overwrite active work.

## Decision log

- 2026-10-25 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-25 · Epic Manager · **Scope and delivery**
  Chose Deliver one vertical feature, feat_024_001, for backlog brief authoring-field edits, a new PR/MR, and post-merge board/plan/activation coherence. Keep identity and lifecycle metadata system-managed; preserve the existing path and untouched content..
  Rationale: The user outcome is incomplete if an edit PR exists but the board or subsequent activation still uses the old brief. Reusing the existing brief form, validation and Git/forge flow minimizes scope while supporting every existing authoring field and additional human-authored Markdown.
  Honors: Edit button; all brief-authoring fields including all five role models and reasoning; new review PR; updated board; frugal engineering and stable epic identity..

- `dec_002` · 2026-10-25 · Epic Manager · **Approved backlog content and provenance**
  Chose Extend backlog precedence narrowly so merged remote brief revisions supersede stale local backlog copies consistently for board, plan and activation; retain active/completed/live-worktree authority and diagnose unpublished local-content conflicts..
  Rationale: Current snapshot import omits every local epic ID and activation prefers local HEAD. Leaving those rules unchanged would hide merged edits or activate an older brief. The correction must not mutate operator checkouts or overwrite in-flight lifecycle state.
  Honors: Board updates after merge; same epic identity; approved source provenance; existing sync cadence and human activation gate; protection of active work..
## Amendment log

_(none)_
