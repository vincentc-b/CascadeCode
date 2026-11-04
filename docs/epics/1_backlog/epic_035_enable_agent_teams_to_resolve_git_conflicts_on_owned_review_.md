---
id: epic_035
title: Enable agent teams to resolve Git conflicts on owned review branches
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
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Enable agent teams to resolve Git conflicts on owned review branches

## Intent

Feature and Epic Teams need a scoped way to inspect real Git history, rebase an owned open MR branch, resolve code conflicts, test, and push the same branch. On 2026-11-04 the epic_031 team could see only plan.md in a read-only scratch turn when asked to unblock PRs #147 and #148; the Feature Team had the same limitation. The operator had to do both rebases outside Cascade. Support both explicit human requests and recovery actions routed by epic_031.

### Success criteria

- An assigned Feature or Epic Team can inspect the actual source and target refs, affected paths, review identity, and owned worktree without an operator shell.
- A scoped resolution turn can fetch, rebase, edit semantic conflicts, run relevant tests, and update the existing open MR branch with a remote-head lease. PR #147 resolves its action_recovery.py conflict; PR #148 completes its clean rebase.
- The Feature Team can update its own MR branch; the Epic Team can handle Epic-owned and explicitly assigned child Feature branches. A cross-feature decision is handed to one accountable owner.
- Changed remote heads, dirty unrelated files, failed tests, missing Git permissions or credentials, and ambiguous semantic choices stop with durable, actionable War Room blockers. Duplicate requests and restarts do not duplicate commits, pushes, reviews, or completion events.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

- Extend epic_031 recovery action identity, routing, and War Room state; accept operator chat requests even before a lifecycle command fails.
- Keep ordinary planning scratch turns read-only. Provide a repository-backed, owned resolution turn or supervisor-mediated Git tools with access to linked .git/worktrees metadata.
- Permit --force-with-lease only for the owned source of an open review, after verifying its recorded remote SHA. Never rewrite target Epic or trunk branches, bypass review/lifecycle gates, discard user files, or expose unrelated checkouts. This narrowly revises epic_031's blanket no-force-push rule.
- Preserve the same PR and accepted-review provenance; recheck branch heads and authorization before each mutation. Cover Codex and other supported providers.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-04 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
