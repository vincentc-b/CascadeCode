# CascadeCode

Cascade coordinates engineering work through **epics → features → tasks**.
Persistent planning teams maintain Markdown work records; task agents implement
bounded changes. A local War Room shows plans, architecture, execution, review,
and recovery. Git branches and your forge's reviews provide delivery boundaries.

## Prerequisites

- Python 3.12 or newer and Git, with your Git author name and email configured.
- A Git repository for the product, with a committed trunk branch (`main` is the
  simplest choice).
- One supported provider: Cursor through the installed Python SDK, or a `claude`
  or `codex` executable available on `PATH`. Install and authenticate your chosen
  provider separately; Cascade does not install provider CLIs.
- For the normal remote review workflow, a GitHub or GitLab remote and an
  authenticated `gh` or `glab` executable with access to that repository.
- For rendered C4 architecture reviews, Docker and the pinned Structurizr image
  described under [Architecture review](#architecture-review).

Cascade runs locally. Model requests use the selected provider. Credentials are
resolved from provider environment variables (`CURSOR_API_KEY`,
`ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`), the user credential store, or supported
CLI sessions. Keep credentials out of the product repository and `cascade.toml`.

## Install Cascade

From a checkout of this repository, create a dedicated environment and install:

```bash
python3.12 -m venv ~/.venvs/cascade
source ~/.venvs/cascade/bin/activate
python -m pip install /absolute/path/to/CascadeCode
cascade --help
```

Keep that environment active when running Cascade. For development on Cascade
itself, use `python -m pip install -e '.[dev]'` from this checkout instead.

## Initialize a product repository

For a new product:

```bash
mkdir my-product
cd my-product
git init -b main
cascade init
```

For an existing product, check out its trunk and run `cascade init` there. You can
also pass `--root /absolute/path/to/my-product` to `init` and `up`.

Initialization creates:

```text
cascade.toml                       Provider and automation settings
skills/design/SKILL.md              Design ownership and maintenance policy
skills/design/templates/DESIGN.md   Starting point for project designs
skills/roles/*/SKILL.md             Agent role playbooks
docs/epics/{1_backlog,2_active,3_completed}/
docs/features/{1_backlog,2_active,3_completed}/
docs/tasks/{1_backlog,2_active,3_completed}/
```

It also adds runtime ignore entries to `.gitignore`. It does not start agents,
create a remote, commit files, or write a placeholder project `DESIGN.md`.
Rerunning `cascade init` installs missing guidance while preserving existing
configuration, custom playbooks and templates. Existing files are not upgraded
automatically; review upstream guidance changes when upgrading Cascade.

Git does not track empty directories. Run `cascade init` after cloning a product
repository to recreate any empty board columns.

## Configure providers and commit the foundation

Edit the generated `cascade.toml`. Select a provider and real model IDs available
to your account for each tier. For example, replace the placeholders below:

```toml
task_parallelism = 4

[automation]
enabled = true
poll_seconds = 15
remote = "origin"

[providers]
default = "codex"

[providers.codex]
epic = "<available-model-id>"
feature = "<available-model-id>"
task = "<available-model-id>"
```

Blank model settings are intentional in the generated file: they are not an
automatic model selection. The War Room provides provider/model selection and
availability feedback. Configure all three tiers, even if the first brief
overrides its epic models; child work does not simply inherit those selections.
Additional provider tables can remain in the configuration.

Write a short product README describing purpose and local development commands.
If a system already exists, document its current design using the installed
template and skill. For an empty repository, the first planning team can establish
design boundaries from the brief and maintain them as implementation proceeds.

Commit the foundation before starting work:

```bash
git add .gitignore cascade.toml skills README.md
git commit -m "Initialize product and Cascade guidance"
```

Include `DESIGN.md` and existing source files if you created or changed them.
For the normal forge workflow, create an empty remote repository, then connect it
and push (replace the URL):

```bash
git remote add origin <your-repository-url>
git push -u origin main
```

Use your actual trunk name for an existing repository. Cascade selects `main`
when present; otherwise it must be able to resolve a unique non-integration
trunk. Run the supervisor from that trunk, not an `epic/*`, `feat/*`, or `task/*`
branch.

## Start and deliver the first epic

```bash
cascade up
```

Open **http://127.0.0.1:8765**. Use `--port` to select another port.

1. **Create brief.** Describe the intended outcome, success criteria, constraints,
   and non-goals. Select the provider and planning models. Brief submission opens
   a review on a brief branch targeting the product trunk.
2. **Merge the brief review.** Wait for polling or select **Pull main** to refresh
   the backlog, then activate the epic.
3. **Review the plan.** The epic team develops its plan and feature breakdown.
   Review requirements, scope, dependencies, proposed architecture, and open
   questions. Ask for revisions through the team's comments. Select **Approve
   plan** when the plan is ready.
4. **Let teams execute.** With automation enabled, eligible features dispatch and
   feature teams create tasks. Task agents implement and test scoped changes.
   Monitor progress, provider blockers, and recovery state in the War Room.
5. **Review delivery.** Feature reviews target the owning epic branch; review
   feedback returns to the team for follow-up work. Review the epic's final
   implementation review into trunk and resolve outstanding closure checks.
   Approval of a plan is separate from approval of its delivered implementation.

The usual branch shape is `task/* → feat/* → epic/* → main`. Follow the review
links and readiness state shown by the War Room rather than moving work records
between directories by hand.

Stop the foreground supervisor with Ctrl-C; restart with `cascade up` from the
same trunk. Durable work records and runtime state support continuation.
New workspaces enable automation. Setting `[automation].enabled = false` opts
into manual lifecycle controls; it does not configure providers or disable
independently configured health audits. Some delivery paths support local
operation without a forge; the brief-to-review walkthrough above requires one.

## Keep documentation useful

| Document | Purpose |
|---|---|
| `README.md` | Getting started, configuration, development, operation, and navigation. |
| Root `DESIGN.md` | Current system goals, shared contracts, architecture boundaries and durable rationale. |
| Child `DESIGN.md` | Current behavior, interfaces, state and decisions owned by a meaningful subsystem. |
| Epic / feature / task records | Delivery scope, IDs, dependencies, plans, revisions, decision history, test results and closeout. |

Design documents explain the system as it currently works. Use stable semantic
requirement and decision IDs such as `REQ-QUEUE-001`; give each one a single
owning design. Parent designs link to child detail instead of duplicating it.

Keep "introduced by epic …", delivery dates, progress logs and implementation
chronology in work records. For example, a design should say "Retries use a
durable checkpoint to avoid duplicate delivery"; the task record can explain
when and why that behavior was implemented. Domain/schema examples may contain
IDs when those IDs are necessary to explain the product itself.

Planners assign affected designs and diagram updates; implementers reconcile
them with actual code; reviewers check them before sign-off and closeout.
Closeout records list designs reviewed, verification, explicit gaps and justified
no-change decisions. These are agent review requirements, not an automatic
semantic lint gate. Read the [design skill](skills/design/SKILL.md) and
[template](skills/design/templates/DESIGN.md) for the complete contract.

## Architecture review

Use C4 views for significant architecture and focused behavior diagrams for
flows or recovery. Maintain source links, requirement/decision ownership, and
verification alongside code. A successful render alone does not prove that the
model describes the implementation.

The renderer expects its pinned image to be available locally. From the active
Cascade environment, pull the image selected by the installed version:

```bash
python -c 'import subprocess; from cascade.workspace.c4_render import STRUCTURIZR_IMAGE; subprocess.run(["docker", "pull", STRUCTURIZR_IMAGE], check=True)'
```

The War Room exposes paired plan/design/C4 review and branch architecture
browsing. Review published artifacts at their pinned revisions; do not replace
accepted snapshots to make a check pass. Model/source contracts and local
rendering are described in the [workspace design](cascade/workspace/DESIGN.md).

## Separate tracking repositories

Start with colocated code and work records unless you need separate storage.
The product configuration can select a tracking repository using the top-level
`tracking_repository` setting (local path or Git remote). Optional
`[architecture].destination = "tracking"` also places architecture documentation
there; the default is `"target"`. Configure these before starting the supervisor.
The target remains the product code repository. See the
[repository configuration implementation](cascade/workspace/project_config.py)
and [workspace design](cascade/workspace/DESIGN.md) for routing details.

## Troubleshooting and development

- **Missing board or playbooks:** run `cascade init`, review the new files, and
  commit them so integration branches can use them.
- **No model turn starts:** check provider availability, authentication and tier
  model settings; inspect the War Room's specific blocker before retrying.
- **Trunk cannot be resolved:** make the initial commit and check out `main` or
  the repository's unambiguous product trunk.
- **Brief missing from backlog:** confirm its review is merged into the configured
  remote trunk, then refresh with **Pull main**.
- **Architecture rendering unavailable:** check Docker and the pinned local image;
  retain the reported verification gap until rendering succeeds.

For Cascade contributors, install the development extra and run relevant tests:

```bash
python -m pytest tests/workspace/test_init.py tests/watchdog/test_role_skills.py
```

[DESIGN.md](DESIGN.md) describes Cascade's own architecture. The `tests/` tree
contains unit, integration and browser checks; some suites require additional
tools or services. Run the checks relevant to the subsystem you change.
