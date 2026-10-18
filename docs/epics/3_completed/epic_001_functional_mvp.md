---
id: epic_001
title: Functional MVP
tier: epic
status: completed
parent: null
children:
- feat_001
- feat_002
- feat_003
- feat_004
- feat_005
- feat_006
- feat_007
- feat_008
- feat_009
- feat_010
- feat_011
- feat_012
- feat_013
- feat_014
- feat_015
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-09'
updated: '2026-10-18'
---

# Functional MVP

Ship a local CascadeCode that can run one real Epic → Feature → Task loop against this repo. The operator talks in a War Room, plans live as markdown on a filesystem board, and nothing is implemented unless the human or the Boss dispatches it.

This epic is **active** (human, 2026-10-09). feat_001 through feat_015 are completed ([feat_015](../../features/3_completed/feat_015_provider_backends.md) — provider backends and credentials). The epic file stays in `2_active` until the human confirms epic completion (`confirm_epic_complete`).

## Intent

An operator on this machine can:

1. Open a local UI bound to localhost.
2. Activate this epic (or another) themselves.
3. Sit with an Epic Team that mints Feature specs into backlog and stops.
4. Dispatch a Feature (human or Boss). Drop in, comment, read the decision log.
5. Watch a Feature Team lock APIs and mint Tasks into backlog — never into `2_active`.
6. Adjudicate a `propose_epic_amendment` in a split-diff pane.
7. Dispatch a Task. A SWE agent commits on `task/{id}`. The operator merges locally.
8. See cards move. Features and the Epic cannot close with open comment threads.

While this epic is still open, the same operator can also:

9. Run each roster role through a local provider backend (Cursor SDK, or the Claude / Codex CLI if that binary is already on this machine), with an explicit provider and model id on every call. Cascade does not install those CLIs. Remote agent VMs are out.
10. Set project default models *per provider* for epic agents, feature agents, and task agents, and override provider or model on a single epic, feature, or task. Sign in from the War Room so the operator does not edit `.netrc` or a file in the workspace.
11. Collapse completed feature and task cards, and focus the board on one epic's features and one feature's tasks.
12. Open any epic, feature, or task plan from the board via **View plan** — rendered markdown in the War Room, including Mermaid diagrams when the viewer bundles Mermaid locally.
13. Run every roster role with default in-repo philosophy playbooks (frugal engineering; PM/EM/developer/reviewer briefs mapped onto Cascade roles), so agents optimize for reliability and delivery speed rather than vanity coverage or pedantic review.
14. Point Cascade at this repo or another local git repo. Agents start only on authorized kickoff edges. An active epic lives on `epic/{id}`, an in-progress feature lives on `feat/{id}`, and tasks are parallel branches into that feature. The War Room reads the worktree dispatch already created. Clicking a card does not check out a branch in the operator's directory. The supervisor shows which features are in flight and which paths overlap.

Success is that loop, on this repo or on another local git repo the operator points Cascade at. Success is **not** a hosted product, a GitLab integration, auto-merge, or one supervisor driving several repos.

## Macro-architecture

Four process kinds, one local repo:

```
localhost UI ──► workspace principals (Human, Boss)
                      │
                      ▼
                 watchdog + queue     (deterministic)
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
     Epic graph  Feature graph  Task graph
          │           │           │
          └───────────┴───────────┘
                      │
                      ▼
              /docs board + git
```

- **Board** (`/docs/{epics,features,tasks}/{1_backlog,2_active,3_completed}`) is lifecycle. Folder membership is status. No parallel status database.
- **Plans** are markdown + YAML frontmatter. Edits are local git commits. Children pin `parent_rev` to a SHA.
- **Queue** (`/docs/_queue/{graph_id}.jsonl`) is the only cross-graph channel. Typed events only. No shared transcripts.
- **Comments** live in `/docs/_comments/{doc_id}.jsonl`, not in the plan body.
- **Watchdog** is not an LLM. It watches the board, enforces dispatch law, boots and tears down graphs.
- **Graphs** are LangGraph subgraphs, one per work object, separate checkpointers.
- **Models.** Each roster role calls a local provider backend with an explicit provider and model id. Project defaults live in `cascade.toml` per provider. An epic, feature, or task may override them. Boot resolves both ids. The agent does not pick another provider or model.
- **UI** is local only. Default home is the Epic War Room. Feature rooms exist after attach. Task graphs have no room. The board can collapse completed columns and lens features and tasks by the epic or feature in focus. Each board card exposes **View plan** to read the on-disk markdown body (Mermaid supported in the renderer). For an in-progress epic or feature, that disk is the team's integration worktree. Attach and View plan do not check out a branch in the operator's directory.

Planning teams write artifacts. They do not start the next machine.

## Cross-module constraints

1. **Local only.** UI binds `127.0.0.1`. No cloud checkpointer, no remote agent runtime, no GitHub/GitLab client. Task output is a local branch. A provider token authenticates a local backend; it does not start a hosted agent that outlives the turn.
2. **Filesystem is truth.** Agents and UI both watch directories. Inventing a second board is a defect.
3. **Dispatch law.** Epic → `ready_to_plan` / `2_active`: human only. Feature planning start and Task dispatch: human or Boss. Epic Team and Feature Team have no dispatch tool and cannot `mv` a child into `2_active`.
4. **Dependencies.** `depends_on` on the `.md` (frontmatter **and** body). Dispatch is illegal until every listed ID is in `3_completed`. Cycles fail validation.
5. **Parallelism.** `cascade.toml` `task_parallelism` (default 4). Watchdog counts Tasks in `2_active` whose status is `active` (not `blocked`). Over-cap dispatches wait; they do not start.
6. **Git versions plans.** No integer `rev`. `parent_rev` is a commit SHA. Amendment accept commits the Epic and sends that SHA down.
7. **Context isolation.** A graph loads only its doc, allowed parents, its comments, and its queue. Path sandbox enforces tool scopes. Prompting is not enough.
8. **Decisions outlive chat.** Locking a constraint, API, type, flow, or amendment requires `record_decision` on the owning `.md`.
9. **Comments default to non-blocking.** Any open human thread still blocks Feature/Epic completion. A human (only) may mark a comment `blocking`, which pauses `mint_task` on that Feature. It does not freeze dispatch of already-minted Tasks. Agents cannot set `blocking`.
10. **Task skills, not a stack enum.** A Task may list in-repo `SKILL.md` paths. Empty list = general SWE agent. Feature Team may set them at mint; Human/Boss may override at dispatch. Missing or out-of-repo paths fail dispatch. No classifier, no `cuda|cpp|python` label.
11. **Failure policy.** Infra/tool flakes inside a live Task subgraph retry at most twice, then `TaskFailed`. Test or spec misses fail closed immediately (no intra-run retry). `TaskFailed` toasts Feature room + War Room, sets status `blocked` (file stays in `2_active`), and tears the graph down. `blocked` does not count toward the parallelism cap. Re-dispatch is a new Human or Boss `dispatch_task` — Feature/Epic cannot restart. The Boss may propose a retry; it must not auto-fire `dispatch_task` on a failed id.
12. **Explicit local backend.** Roster roles infer through a local provider backend (`cursor`, `claude`, or `codex`). Every call carries a provider id and a model id. Cloud agent VMs, remote checkpointers, and remote brokers stay forbidden. Cascade does not install provider CLIs; a missing binary fails the turn.
13. **Model defaults are per provider.** `cascade.toml` names a default provider and, for each provider, default models for epic agents, feature agents, and task agents. The work document may override provider and/or model. A feature does not inherit its epic's override. Unset config fails closed. It does not silently become `auto`.
14. **Board lens.** The War Room can collapse completed columns. Features shown belong to the selected epic, or to epics in `2_active` when none is selected. Tasks shown belong to the feature selected on the board. The read API still returns the full board.
15. **One workspace, one repo.** A Cascade process supervises a single git root. The tool and that root may be different directories. Agents start only on an authorized kickoff edge. Minting a file and polling the board do not start an agent. One process does not orchestrate multiple repos.
16. **Stacked integration lines.** The product trunk holds the human brief and, later, a promoted epic. `activate_epic` cuts `epic/{id}` from that brief. `dispatch_feature` cuts `feat/{id}` from the epic branch. `dispatch_task` cuts `task/{id}` from the feature branch. Each live epic and feature has a worktree under `.cascade/worktrees/`. The operator checkout stays on the trunk. Task branches merge into the feature, the feature merges into the epic branch once, and the epic branch merges to the trunk when the human promotes it. The supervisor reports in-flight features, the paths they change, and path overlaps. Overlap does not dispatch or merge.
17. **Provider credentials stay off the board.** Tokens live in the `up` process environment (still first) or a user-level store the War Room login pane writes (`~/.cascade/credentials`, mode `0600`). An already-logged-in Claude or Codex CLI session is a third source. Never `.netrc`, never `cascade.toml`, never a file in the workspace. One missing credential fails that provider's turn; Cascade does not silently switch providers.

## Core dependencies

| Mandate | Why |
|---|---|
| Python 3.12+ | Supervisor, watchdog, LangGraph runtimes |
| LangGraph | One subgraph per work object; checkpointer per id |
| Local git | Plan versioning; integration branches `epic/{id}`, `feat/{id}`, `task/{id}` |
| `cascade.toml` | Supervisor config; planning agents do not use it to self-start |
| pytest | Acceptance for board, watchdog, graphs |
| localhost HTTP for the UI | Operator machine only; Feature `feat_003` picks the UI toolkit |
| `cursor-sdk` (Python) | Default Cursor backend; provider and model id required on each call |
| Optional `claude` CLI | Claude backend when the operator already has Claude Code on PATH |
| Optional `codex` CLI | Codex backend when the operator already has Codex on PATH |
| `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Process environment, first credential source; never a workspace file |
| `~/.cascade/credentials` | User-level store written by War Room login; mode `0600`; not per-project |

Forbidden: remote brokers, cloud agent VMs, cloud checkpointers, installing provider CLIs from Cascade, writing tokens to `.netrc` or the repo, and writing task code onto the trunk or the epic branch instead of `task/{id}`. Feature code reaches `epic/{id}` only through the feature merge. Model inference is a local provider backend (feat_009, feat_015) with provider and model ids resolved by feat_010 / feat_015.

## Feature breakdown

`depends_on` edges are also in each Feature's frontmatter.

| ID | Title | Depends on | Role |
|---|---|---|---|
| [feat_001](../../features/3_completed/feat_001_board_schema_git.md) | Board, document contract, git plan store | — | Truth on disk |
| [feat_002](../../features/3_completed/feat_002_watchdog_queue_dispatch.md) | Watchdog, queue, dispatch law | feat_001 | Deterministic supervisor |
| [feat_003](../../features/3_completed/feat_003_local_war_room.md) | Local War Room UI | feat_001, feat_002 | Human home |
| [feat_004](../../features/3_completed/feat_004_epic_team.md) | Epic Team graph | feat_002, feat_003 | Strategic hub |
| [feat_005](../../features/3_completed/feat_005_feature_team.md) | Feature Team, comments, drop-in | feat_004 | Tactical hub |
| [feat_006](../../features/3_completed/feat_006_amendment_protocol.md) | Amendment protocol | feat_005 | Upward negotiation |
| [feat_007](../../features/3_completed/feat_007_task_execution.md) | Task execution, local branches | feat_002, feat_005 | Ephemeral SWE |
| [feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) | Boss agent and completion rollup | feat_003, feat_006, feat_007 | Dispatch lieutenant + closeout |
| [feat_009](../../features/3_completed/feat_009_cursor_agent_backend.md) | Cursor agent backend | feat_004, feat_005, feat_007, feat_008 | Local Cursor call with a required model id |
| [feat_010](../../features/3_completed/feat_010_model_defaults_and_overrides.md) | Model defaults and overrides | feat_009 | Project defaults; document may override |
| [feat_011](../../features/3_completed/feat_011_board_focus_and_collapse.md) | Board focus and collapse | feat_003 | Collapse completed; lens by epic and feature |
| [feat_012](../../features/3_completed/feat_012_plan_viewer.md) | Plan viewer (View plan) | feat_003 | Render plan markdown + Mermaid from the board |
| [feat_013](../../features/3_completed/feat_013_role_skills_and_frugal_engineering.md) | Role skills and frugal engineering philosophy | feat_004, feat_005, feat_007, feat_009 | Default role playbooks for roster agents |
| [feat_014](../../features/3_completed/feat_014_workspace_contract.md) | Workspace contract and agent kickoff | feat_002, feat_003, feat_006, feat_007, feat_008, feat_009, feat_010, feat_012 | Stacked branches; kickoff; War Room reads the dispatch worktree; flight overlaps |
| [feat_015](../../features/3_completed/feat_015_provider_backends.md) | Provider backends and credentials | feat_009, feat_010, feat_014 | Local Cursor / Claude / Codex; per-provider defaults; War Room login; no remote agent runtime |

feat_001 through feat_015 are completed. Epic closeout still requires an explicit human confirm; do not auto-close this epic.

## Open questions

None. DESIGN.md §15 calls are locked (`dec_005`–`dec_007`).

## Decision log

- `dec_001` · 2026-10-09 · Epic Architect · **Macro-architecture**
  Chose filesystem board + LangGraph-per-object + local git as the MVP skeleton.
  Rationale: matches DESIGN.md; anything hosted is a non-goal.
  Honors: DESIGN.md §2, §3, §6.

- `dec_002` · 2026-10-09 · Epic Architect · **Feature breakdown**
  Eight features, not a single "build the product" feature. Split supervisor (feat_002) from UI (feat_003) from each graph tier so dispatch law can ship before any LLM loop.
  Rationale: a Task agent must not exist until mint-into-backlog-only is already enforced.
  Honors: DESIGN.md §5.0.

- `dec_003` · 2026-10-09 · Epic Architect · **Core dependencies**
  Mandated Python 3.12 + LangGraph + local git. Left UI toolkit to feat_003.
  Rationale: graphs and watchdog share a language; UI is a presentation choice, not a cross-module ABI.
  Honors: local-only constraint.

- `dec_004` · 2026-10-09 · Epic Manager · **Lifecycle**
  Minted feat_001–feat_008 into `/docs/features/1_backlog/`. Epic remains `backlog`. Did not set `ready_to_plan`.
  Rationale: only the human may activate an epic.
  Honors: DESIGN.md §5.0.

- `dec_005` · 2026-10-09 · Human · **Comments**
  Comments default to non-blocking. Human may mark `blocking`, which pauses `mint_task` only. Dispatch of already-minted Tasks is unchanged. Agents cannot set `blocking`. Open human threads still gate Feature/Epic completion.
  Rationale: review can halt decomposition without freezing work you already chose to run.
  Honors: human-mobile review; dispatch law.

- `dec_006` · 2026-10-09 · Human · **Task skills**
  Dropped the `stack` enum. Tasks carry optional in-repo `SKILL.md` paths. Empty = general agent. Mint may set; dispatch (human/Boss) may override. Missing paths fail dispatch.
  Rationale: an enum is a label with no behavior; a skill path is the playbook the SWE agent should load.
  Honors: Task reads its spec; no classifier.

- `dec_007` · 2026-10-09 · Human · **Failure policy**
  Live-run infra flakes retry twice then fail. Spec/test misses fail closed immediately. `TaskFailed` → `blocked` in `2_active`, slot not counted. Re-dispatch is Human or Boss only; Boss proposes, does not auto-fire. Feature/Epic cannot restart a Task.
  Rationale: retrying a bad spec wastes a slot; a torn-down graph is a new dispatch; silent Boss retries violate "nothing implements without an order."
  Honors: dispatch law; parallelism.

- `dec_008` · 2026-10-09 · Human · **Activation**
  Human activated this Epic and dispatched feat_001. `parent_rev` left null until the first local commit exists.
  Rationale: human-only Epic gate; feat_001 has no Feature dependencies.
  Honors: §5.0 dispatch law.

- `dec_009` · 2026-10-10 · Feature Architect · **feat_008 dispatched**
  Boss and completion rollup (feat_008) moved to `2_active`; tasks task_038–task_044 minted in backlog. Boss is a human-delegated dispatch lieutenant (order-driven, no auto-drain on sight); merge and rollup gates honor open human comments and explicit epic confirm.
  Rationale: closes the Epic → Feature → Task loop with deterministic supervisor rules from DESIGN.md §12.
  Honors: §5.0.1, §11, §12.

- `dec_010` · 2026-10-10 · Feature Architect · **feat_008 completed**
  Boss view, order consumer, human merge, feature rollup with comment/closeout gates, epic-ready prompt with human `confirm_epic_complete`, and orphan flags shipped; feat_008 and tasks task_038–task_044 moved to `3_completed`. Epic remains `active` in `2_active` until the human confirms epic completion.
  Rationale: MVP feature work is done; epic lifecycle close is a separate human gate per DESIGN.md §12.
  Honors: §12; feat_008 closeout.

- `dec_011` · 2026-10-10 · Human · **Model backend, defaults, board lens**
  Added feat_009, feat_010, and feat_011 to this epic's backlog. Inference is a local Cursor agent that must be given a model id. `cascade.toml` holds tier defaults for epic, feature, and task agents; the work document may override, and a feature does not inherit its epic's model. The Boss uses an optional project default, otherwise the epic tier default. The board may collapse completed columns. Features follow the selected epic, or active epics when none is selected. Tasks follow the feature selected on the board.
  Rationale: the shipped loop has no model call, and the completed columns hide the live work. Defaults are guidance for unspecified documents; an explicit id on the call keeps the backend from inventing one.
  Honors: local-only; filesystem is truth; dispatch law.

- `dec_012` · 2026-10-10 · Feature Architect · **feat_009 dispatched**
  Cursor agent backend (feat_009) moved to `2_active`; tasks task_045–task_048 minted in `docs/tasks/1_backlog/`. Local Python SDK adapter with required caller-supplied model id; planning scratch cwd; SWE worktree turn with path gate and existing git tools; graph wiring replaces quote replies without new dispatch primitives.
  Rationale: split adapter, sandbox, SWE turn, and graph integration so SWEs can parallelize after the adapter lands.
  Honors: local-only; dispatch law; dec_011.

- `dec_013` · 2026-10-10 · Feature Architect · **feat_009 completed**
  Local Cursor agent adapter (`run_role`, local async client, dispose-on-return), planning scratch sandbox, SWE worktree turn with path gate and failure classification, and graph wiring replacing quote replies shipped; feat_009 and tasks task_045–task_048 moved to `3_completed`. Epic remains `active` in `2_active` until the human confirms epic completion.
  Rationale: roster roles now call the local Python SDK with a required caller-supplied model id; feat_010 and feat_011 remain backlog.
  Honors: local-only; dispatch law; dec_012.

- `dec_014` · 2026-10-10 · Human · **Plan viewer**
  Added feat_012 to backlog: **View plan** on each epic, feature, and task board row opens a localhost plan page that renders the document body (existing `GET /api/doc/{id}`), with Mermaid diagrams when a Mermaid build is vendored under War Room static assets. Read-only; no new plan store.
  Rationale: operators need to read specs without leaving the War Room or raw JSON; plans already use Mermaid in feature docs.
  Honors: filesystem is truth; local-only UI.

- `dec_015` · 2026-10-10 · Feature Architect · **feat_012 completed**
  Plan viewer shipped: `GET /plan/{id}`, client markdown + Mermaid (vendored), **View plan** on all board rows. feat_012 and task_056–task_058 moved to `3_completed`. Epic remains active until human confirm.
  Rationale: closes the plan-viewer scope from dec_014; epic lifecycle close is still a separate human gate.
  Honors: filesystem is truth; local-only UI; dec_014.

- `dec_016` · 2026-10-13 · Human · **Role skills / frugal engineering**
  Added feat_013 to backlog: in-repo `skills/roles/**/SKILL.md` playbooks encoding frugal engineering + PM / EM / developer / reviewer briefs; map onto existing roster (`epic_manager`/`feature_lead` ← PM, `boss` ← EM, `swe` ← developer+reviewer, architects ← shared core). Default role skills load on every matching turn; Task frontmatter `skills` remain additive specialization. No new roster node for Code Reviewer in v1 unless dogfooding requires an amendment.
  Rationale: roster agents currently have model ids but almost no shared engineering philosophy in context; Task `skills` alone do not steer planning roles, and empty Task `skills` meant a blank SWE until feat_013 (now general SWE plus default philosophy playbooks; see DESIGN.md §4.1).
  Honors: task skills not a stack enum (`dec_006`); filesystem is truth; skill content is context only.

- `dec_017` · 2026-10-12 · Human · **Workspace contract and kickoff**
  Added feat_014 to backlog. Cascade is a tool pointed at one git workspace (this repo or another). `init` scaffolds a board and does not start agents. `up` starts the War Room and the watchdog on that root. A model turn runs only on an authorized edge: human epic activation, human or Boss feature/task dispatch, a human message or comment on a live team, a queue event that team must answer, or resume of an in-flight turn. Minting, backlog files, board views, and idle polls do not kick an agent off. Restart re-attaches legal `2_active` graphs and does not write a new dispatch. One process, one repo. The backend token is `CURSOR_API_KEY` in that process environment, shared by every role in the workspace. It is not stored per project and it is not read from `.netrc`. The board is whatever branch is checked out at the workspace root; Cascade does not scan other branches and does not require the name `main`. Human merge lands only on the unique non-`task/*` mainline while that branch is checked out.
  Rationale: dispatch law already says who may start work, but not when a model actually runs, or how an operator uses the tool outside this checkout. Those are one contract.
  Honors: dispatch law; local-only; Boss is order-driven; filesystem is truth.

- `dec_018` · 2026-10-13 · Human · **Stacked integration lines**
  Supersedes the branch rule in `dec_017`. The product trunk holds the human brief. Activation cuts `epic/{id}` and a worktree; the trunk copy becomes a pointer. Feature dispatch cuts `feat/{id}` from the epic branch. Task dispatch cuts `task/{id}` from the feature branch. Tasks merge into the feature, the feature merges into the epic branch once, and the human promotes the epic branch to the trunk. The operator checkout stays on the trunk. Attach and View plan read the worktree created at dispatch; a click does not check out a branch. A backlog feature has no worktree: View plan reads the epic worktree, and Attach is refused. The supervisor reports in-flight features, changed paths, and path overlaps, and does not merge or dispatch because of them.
  Rationale: one checkout cannot be both the live board and several unmerged lines of work. Stacking the merge parents keeps features atomic and the epic self-contained, and keeps parallel tasks on their own branches.
  Honors: dispatch law; filesystem is truth; context isolation; local-only.

- `dec_019` · 2026-10-16 · Human · **Provider backends and credentials**
  Added feat_015 to backlog. Roster roles call a local backend named `cursor`, `claude`, or `codex`. Cursor stays the Python SDK. Claude and Codex are their CLIs, used only when already on PATH — Cascade does not install them. Each provider has its own epic / feature / task model defaults. A document may override provider and/or model; children do not inherit. Credentials: process env first, then `~/.cascade/credentials` written by the War Room login pane, then an existing CLI session. Never `.netrc`, never the workspace. Remote / cloud agent VMs stay forbidden: an epic lasts days, a hosted agent session does not, and a durable provider conversation would fork memory away from the LangGraph checkpointer (same rejection as feat_009). API tokens authenticate a local turn; they do not start a remote agent. Reviewer remains a SWE skill, not a new roster node.
  Rationale: today's `[models]` table is provider-agnostic ids on a Cursor-only adapter. Operators who already have Claude Code or Codex should use them without editing netrc, and without Cascade pretending a Cursor model id is a Codex model id. Hosted agents cannot be the memory of a multi-day epic.
  Honors: local-only; filesystem is truth; feat_009 one-shot turns; feat_010 fail-closed defaults; feat_013 no extra roster node; feat_014 kickoff and env-first credentials.

## Amendment log

_(empty)_
