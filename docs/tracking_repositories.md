# Tracking repositories

Cascade can keep versioned planning artifacts in the source repository (the
default) or route them to a separate Git repository. This setting changes
planning storage only; it does not turn Cascade into a multi-repository source
orchestration tool.

## Repository roles

- The **target repository** is the checkout passed to `cascade up --root`. It
  owns `cascade.toml` or `cascade.yaml`, `.cascade/` runtime state,
  implementation branches and worktrees, source changes, builds, and tests.
- The **tracking repository** owns the versioned planning tree under `docs/`,
  including epic, feature, and task documents, decision history, and required
  versioned lifecycle metadata.

When the roles are split, normal planning activity reads and commits those
artifacts in the tracking repository. It does not copy the resulting changes
back into the target repository. Source and planning commits are independent:
Cascade does not provide a cross-repository transaction or roll one repository
back when an operation in the other repository fails.

## Configuration

The optional top-level `tracking_repository` value accepts a local checkout
path or a Git remote. Relative local paths are resolved from the directory that
contains the project configuration. Keep exactly one supported project config:
`cascade.toml`, `cascade.yaml`, or `cascade.yml`.

### Colocated mode (default)

Omit `tracking_repository`:

```toml
task_parallelism = 4

[automation]
enabled = true
```

The target and tracking roles then refer to the same checkout, so planning
artifacts remain under `<target>/docs/`. Existing projects need no configuration
change.

### Split mode with a local checkout

```toml
tracking_repository = "../project-planning"
```

The path must name the root of an existing, usable Git checkout. Cascade uses
it in place and does not fetch from or push to any remote it may have. Operators
are responsible for synchronizing a local-path checkout when synchronization is
desired.

### Split mode with a remote

```yaml
tracking_repository: "git@github.com:example/project-planning.git"
```

Git, HTTP, HTTPS, SSH, and scp-style Git references are accepted. Cascade
clones a remote reference into a deterministic managed checkout below
`<target>/.cascade/tracking-repositories/`, reuses that checkout on later
starts, and synchronizes its checked-out branch at startup and after planning
commits.

## Architecture documentation destination

Architecture documentation has an independent destination setting in the
target repository's project configuration. Omitting the table keeps designs
and editable models in the target repository:

```toml
[architecture]
destination = "target"
```

Use the configured tracking repository instead with:

```toml
tracking_repository = "../project-planning"

[architecture]
destination = "tracking"
```

Only `target` and `tracking` are valid. Selecting `tracking` requires an
explicit, usable `tracking_repository`; colocated compatibility mode is not an
implicit tracking selection. Invalid combinations stop configuration or
startup before architecture paths are routed.

### Paths and ownership

For a target-code-relative directory `<directory>`, Cascade resolves exactly
one current design home:

| Destination | Design path | Editable model and fragment root |
|---|---|---|
| `target` | `<target>/<directory>/DESIGN.md` | `<target>/architecture/<target-key>/` |
| `tracking` | `<tracking>/design/<target-key>/<directory>/DESIGN.md` | `<tracking>/architecture/<target-key>/` |

The root directory is represented by `.` and resolves to `<target>/DESIGN.md`
or `<tracking>/design/<target-key>/DESIGN.md`. Enabling this feature does not
replace or rewrite an existing target-root `DESIGN.md`.

The target repository always owns
`architecture/design-mappings.json`, including when artifacts live in the
tracking repository. Its schema-v1 object records one opaque, immutable
`target_repository_key` and a `designs` map keyed by normalized target-code
directory. Each row fixes `code_directory`, `design_owner_directory`, and a
stable `artifact_id`. Meaningful directories may own their design; trivial or
generated directories map to a covering parent. Conflicting owners, duplicate
identities, a changed committed target key, path escapes, and writes or reviews
without a persisted owner fail closed.

### Fixed review references

Consumers should use `ProjectContext.design_path()` and
`editable_architecture_root` for a new artifact, and the architecture ownership
APIs to persist or require its owner. A new design or model review reference
records the target key, target-code directory and owner, owning work,
destination repository identity and role, repository-relative path, and Git
revision. Reads, links, review, and replay then use those recorded fields and
the bytes at the pinned commit. Reference creation requires the reviewed design
or model bytes to exactly match the artifact at destination `HEAD`; a new,
modified, deleted, or otherwise unreadable working artifact cannot be pinned as
reviewed content. Commit the reviewed bytes before creating the reference.

Changing `[architecture].destination` affects only new references. It neither
moves artifacts nor rewrites the target-owned mapping index. An existing review
unit remains at its recorded repository, path, and revision; an unavailable
commit, missing blob, or mismatched repository identity is an error rather than
a retarget. Reconfiguring `tracking_repository` therefore cannot make an old
reference read from the replacement checkout, even if it has a matching path.
This is the location/provenance contract for design rendering, semantic model
processing, review-unit gates, authoring closure, and historical replay.

Known limits: Cascade does not migrate architecture artifacts between
destinations, merge target and tracking changes transactionally, infer durable
identity from a checkout basename, or authorize edits merely because it can
resolve a path. Destination migration is a separate reviewed operation, and
existing scoped editing and owner-amendment rules still apply.

## Prerequisites and non-goals

Before enabling split mode:

1. Initialize the target with `cascade init` and run Cascade from its product
   trunk. The target still needs the standard board directory scaffold at
   startup even though planning documents are routed elsewhere.
2. Prepare a tracking repository with a checked-out branch and at least one
   commit. For a local reference, prepare the checkout yourself. For a remote
   reference, ensure the remote is cloneable and its planning branch exists.
3. Configure Git author identity for commits. For a remote reference, also
   configure non-interactive Git credentials or SSH access in the environment
   that runs Cascade.

Cascade does not create accounts, install or rotate SSH keys, store tokens,
configure credential helpers, choose a conflict resolution, or migrate existing
artifacts. Do not put credentials in `tracking_repository`; prefer a
credential-free remote URL backed by preconfigured Git or SSH access.

## Adopting existing planning artifacts

Changing the setting does not move or merge anything. Adopt an existing board
at a quiet point so there is a single state to transfer:

1. Stop `cascade up` and finish or otherwise reconcile in-flight planning work.
2. Back up both repositories and make sure the intended tracking branch is
   checked out.
3. Copy the target's existing versioned planning artifacts into the same paths
   under `<tracking>/docs/`. Preserve the epic, feature, and task column layout
   and versioned sidecars. Inspect and resolve any files already present in the
   tracking repository; do not assume Cascade will merge them.
4. Review the tracking-repository diff, then commit it. If the configuration
   will use a remote reference, push the adopted commit and verify that a fresh
   clone checks out the intended branch.
5. Add `tracking_repository` to the target's project configuration and start
   Cascade. Confirm in the War Room that the expected board is present before
   resuming work.

The old target copies are ignored for planning once split mode is active; they
are not deleted automatically. Remove or archive them only after verification,
while retaining the target's board directory scaffold required by startup. A
fresh target clone may need `cascade init` to recreate empty scaffold
directories.

## Failure states and recovery

Cascade reports preparation and synchronization failures instead of silently
falling back to the target repository. The failed operation has not completed
successfully, even when a local file or commit is visible.

### Preparation or startup fails

- **Local path missing, not a Git checkout, or below the checkout root:** Fix
  the configured path so it names the checkout root, then restart Cascade.
- **Clone or fetch authentication/reachability failure:** Repair the
  preconfigured Git or SSH access and retry. Cascade does not prompt for or
  repair credentials.
- **Interrupted or invalid managed checkout:** Use the managed-checkout path in
  the error. Inspect it first for local commits or uncommitted work. Preserve
  anything needed, then move the incomplete or mismatched checkout aside and
  restart; Cascade will clone the remote again when its deterministic path is
  absent.
- **Detached checkout or unavailable branch:** Check out or restore the intended
  planning branch in the preserved managed checkout, then retry startup.

Startup stops on these errors. It does not switch to colocated storage.

### Synchronization fails

Remote synchronization fetches the checked-out branch and then applies only a
safe one-way result:

- If the remote is ahead, Cascade fast-forwards the managed checkout.
- If the local branch is ahead, Cascade pushes it.
- If local and remote have diverged, Cascade stops without merging or rebasing.

For divergence or a failed fast-forward, open the managed checkout named in the
error, inspect `git status` and the local/remote history, and reconcile them
using the team's normal Git policy. Leave the intended branch checked out and
the checkout in a usable state, then retry `cascade up` or the original planning
action.

A failed push occurs after the planning commit was created locally. Cascade
preserves that commit in the managed checkout but still reports the planning
operation as failed because remote synchronization is incomplete. Repair remote
access and retry; startup or a repeated planning action will attempt
synchronization again. Do not recopy the board or recreate the preserved commit.

After any interrupted planning action, inspect both `git status` and recent
commits in the tracking checkout before retrying. Preserve unexpected work and
resolve Git state manually. Success in the target repository does not imply
success in the tracking repository, or vice versa.
