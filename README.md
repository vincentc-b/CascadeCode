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

### Run the recovery contract locally

The `Recovery contract` check exercises the real-repository owner journey,
cumulative incident budgets, provider admission, review publication and
independent postchecks. From a fresh checkout, reproduce the CI selection with
only the declared development dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
timeout --kill-after=10s 8m \
  python -m pytest -q \
    tests/test_late_repair_convergence.py \
    tests/task/test_incident_budget.py \
    tests/agent/test_provider_recovery_contract.py \
    tests/test_review_publication_safeguards.py \
    tests/test_review_recovery_journey.py \
    tests/test_review_health.py \
    tests/test_review_rebase.py \
    tests/test_resolution_actions.py \
    tests/watchdog/test_reservations.py \
    tests/watchdog/test_audit_investigation.py \
    tests/watchdog/test_parent_lifecycle_postcheck.py \
    tests/feature/test_publication.py::test_review_recovers_remote_creation_before_local_registry_write \
    --tb=short
```

Exit status `124` means the local eight-minute command bound expired and is a
failure. CI keeps the job-level ten-minute limit and retains only a redacted,
bounded diagnostic tail when the selection fails. The late-repair fixture uses
production Task boot/skill wiring, real Git and validators, and actual worker
restart/postcheck; provider/forge transport and discovery evidence are scripted.
It requires no installed provider CLI. Its synthetic red/green source edit
changes byte length to avoid timestamp-based Python bytecode cache reuse on
fast runners. The gate runs on relevant PRs and on `main`; inspect the exact
merged revision's result rather than relying solely on the PR check.

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

### After merging a review

A green source-branch check is not proof that the final merge result is green.
Check the required CI on the actual merged trunk revision. With automation
enabled, **Pull main** refreshes a read-only remote backlog snapshot; it does
not synchronize the operator's local Git branch. With automation disabled, it
uses the existing fast-forward-only trunk path. When you need the local code
checkout to match the remote trunk, inspect and synchronize it explicitly:

```bash
git branch --show-current
git status --short
git fetch origin main
git rev-list --left-right --count main...origin/main
```

On the checked-out `main`, use `git pull --ff-only origin main` when the incoming
changes can be fast-forwarded without overwriting local work. Substitute the
configured remote/trunk names as needed. If it refuses, preserve local changes
and resolve the divergence through the normal Git review/integration path; do
not reset or force-push. Verify both `git rev-parse main origin/main` values
match after synchronization. Review approval, branch synchronization, the
post-merge CI result, and the running supervisor revision are separate facts.

Epic closeout accepts a cancelled Feature only if cleanup is complete and the
canonical Epic records the exact resolved `continue_reduced_scope` disposition.
The cancelled document remains in `3_completed` with status `cancelled`;
this does not count as delivered implementation or waive other review gates.

Stop the foreground supervisor with Ctrl-C; restart with `cascade up` from the
same trunk. Durable work records and runtime state support continuation.
The editable-source update path can restart the worker under the existing
launcher; it does not replace the already-imported launcher code. If an update
changes the launcher/worker handshake or otherwise requires a new launcher,
stop the complete supervisor gracefully and rerun `cascade up` with the same
workspace, environment, host and port. Check `/api/health` for `serving` and
`automation.ready`, and `/api/board` for a successful board response. An
ordinary local health check does not attest a reviewed runtime repair.
New workspaces enable automation. Setting `[automation].enabled = false` opts
into manual lifecycle controls; it does not configure providers or disable
independently configured health audits. Some delivery paths support local
operation without a forge; the brief-to-review walkthrough above requires one.

### Hand off a reviewed orchestration repair to the runtime

A Task commit, merged review, and running supervisor are separate facts. Use this
procedure when the supervisor itself needs a reviewed Cascade repair. It does not
authorize installation, change a product checkout, or deploy from a Task branch.

1. Record the accepted review URL and its exact source commit. In a separately
   prepared checkout of that reviewed commit, verify both the commit and a clean
   tree before changing the installed runtime:

   ```bash
   git -C /absolute/path/to/reviewed/CascadeCode rev-parse HEAD^{commit}
   git -C /absolute/path/to/reviewed/CascadeCode status --short
   ```

   Record that commit as the expected running revision. Leave the validated
   delivery and its recovery action queued until the post-restart check succeeds.
2. In the terminal that owns `cascade up`, press Ctrl-C once. This invokes the
   supervisor's bounded drain: new mutations are refused, live turns get their
   configured grace period, and remaining turns are cancelled with durable state
   preserved. Wait for the command to exit. A second interrupt escalates to a
   forced stop and should be used only when graceful drain cannot finish.
3. Only with separate installation authority, update the dedicated Cascade
   environment from the reviewed checkout using the installation procedure in
   [Install Cascade](#install-cascade). Do not edit site-packages, import private
   repair functions, hotpatch the old process, or change lifecycle/event files.
4. With the same environment active, create a runtime-authority manifest. This
   command refuses a dirty or stale reviewed checkout, an unknown integration
   commit, or installed Python bytes that differ from the reviewed source. It
   records evidence only; it does not install software or grant installation
   authority:

   The installation actor supplies a version-1 JSON receipt containing
   `accepted_review_url`, `authorized_actor`, `environment`, both absolute
   repository paths and exact revisions, and `installed_source_sha256`. Its
   `receipt_id` is SHA-256 of the canonical JSON body (sorted keys, compact
   separators); `signature` is HMAC-SHA256 of that same body plus `receipt_id`
   using the separately provisioned key (at least 32 bytes). Receipt issuance
   is deliberately outside Cascade and must follow the environment's approval
   and credential policy.

   ```bash
   cascade runtime-bootstrap \
     --reviewed-source /absolute/path/to/reviewed/CascadeCode \
     --integrated-source /absolute/path/to/guarded/integration-checkout \
     --deployment-receipt /protected/signed-deployment-receipt.json \
     --authority-key /protected/installation-authority.key \
     --output /protected/runtime-authority.json
   ```

   A non-editable installation may not live inside a Git checkout. In that case,
   the command binds its installed package bytes to the reviewed checkout rather
   than guessing a revision from the package path.
5. Start from the product trunk with that exact manifest:

   ```bash
   cascade up --root /absolute/path/to/product \
     --runtime-authority /protected/runtime-authority.json \
     --runtime-authority-key /protected/installation-authority.key
   ```

   Verify `curl -fsS http://127.0.0.1:8765/api/health` reports `serving` and that
   `runtime_identity.verified` is `true`. Record its reviewed and integrated
   revisions, signed deployment receipt, installed-source digest, loaded-module
   origins/digests, worker PID, host boot/process-start identity, capability
   generation and timestamp. Cascade revalidates the signed receipt, both clean
   exact checkouts, review ancestry and installed bytes before each spawn. The
   launcher independently reads `/proc`, the selected import root, module bytes
   and its own capability generation before setting `verified`; stale, mixed,
   wrong-root or changed evidence fails closed. Linux `/proc` is therefore a
   prerequisite for deployment proof.
   Starting without `--runtime-authority` remains supported for ordinary local
   operation but reports `runtime_authority_missing` and is not deployment proof.
   With automation enabled, wait for the normal review poll and record the War
   Room review-health outcome for the queued repair. If automation is disabled or
   the forge is unavailable, keep the delivery queued and record the postcheck as
   unperformed; do not manufacture success with an internal Python call.

If the old running code cannot admit the repair, the exact prerequisite is:
gracefully stop that old supervisor, obtain separate authority to install the
reviewed revision, obtain the installation actor's signed deployment receipt and
provisioned trust key, and restart it before retrying the canonical queued
operation. A local Task merge, caller-supplied SHA, unsigned receipt, or healthy
endpoint alone does not satisfy that prerequisite.

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

The plan page has **Epic / feature / task**, **DESIGN.md changes**, and
**C4 diagrams** tabs. The plan tab initially shows the proposed plan, with an
optional comparison to the original brief; the design tab shows changed design
documents with their surrounding context.

C4 diagrams shows one combined diagram: red removals, green additions, amber edits, and
unchanged elements for context. Click a marked element to explore its deeper view.
Click a leaf element or relationship to inspect before/after details; use
**Semantic targets** to inspect expandable elements without navigating.
**Explore selected element** also opens a verified deeper view;
**Level up** returns to its parent. Zoom and pan survive background refreshes;
**Fit** resets the current view. A rewired relationship shows both its old red
connection and its new green connection.

**L1: System context** is the starting view. Click Cascade to open **L2: Containers**;
**Level up** stops at context. **Project landscape** remains an optional overview
in the selector, outside the normal drill-down path. Explicit saved view links
are preserved. Landscape and context can contain the same elements when
the landscape consists of one system and its immediate surroundings. The container
view expands Cascade into Operator CLI, War Room, Service and Repository artifacts.
Identical displayed graphs retain the same layout between views.

The comparison uses committed project/proposal revisions. **Refresh comparison**
reloads the page to obtain new pins; uncommitted architecture edits do not appear
until committed. A first comparison can show a rendering status while its
combined layout is prepared. Merge conflicts are reported explicitly and must
be reconciled before a fresh integration preview can be rendered.

The Architecture tab browses a selected branch at a pinned revision. Drill
through an application's components to see the Code view. Each code box shows
its declaration kind. Select a box to see the symbol and open its pinned source.
The [C4 guide](architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/README.md#integrated-code-level)
explains the labels and maps the views to their source.
Published review and approval evidence remains separate from previews; do not
replace accepted snapshots to make a check pass. Interaction is described in the
[War Room design](cascade/war_room/DESIGN.md#single-diagram-architecture-differences);
model/source contracts and local rendering belong to the
[workspace design](cascade/workspace/DESIGN.md#derived-comparison-rendering).

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
- **Board unavailable: duplicate id:** the error names physical files in a
  checkout. Inspect both against the accepted review and canonical owner before
  reconciling the stale copy; preserve the terminal record, cancellation feedback
  and history. Correct the published source/target tree through normal Git
  integration, then synchronize any affected clean worktree. Do not change a
  document's status or delete an arbitrary duplicate just to make the board load.
- **503 after updating Cascade:** inspect `/api/health` and the local supervisor
  status. If the old launcher rejects the newer worker's readiness message,
  gracefully stop and restart the complete launcher from the updated, intended
  environment instead of repeating worker-only startup attempts. Confirm both
  health and board availability after restart.
- **Architecture rendering unavailable:** check Docker and the pinned local image;
  retain the reported verification gap until rendering succeeds.

For Cascade contributors, install the development extra and run relevant tests:

```bash
python -m pytest tests/workspace/test_init.py tests/watchdog/test_role_skills.py
```

[DESIGN.md](DESIGN.md) describes Cascade's own architecture. The `tests/` tree
contains unit, integration and browser checks; some suites require additional
tools or services. Run the checks relevant to the subsystem you change.
