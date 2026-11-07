# task_039_002_005 — Real smoke acceptance record

## Result

**Acceptance is blocked as of 2026-11-07.** No project-local dependency was
installed, no container was created or run, and no adapter-feasibility proof
was executed. This record must not be used as successful smoke evidence.

The task dispatch and approved Epic/Feature plans grant implementation access,
not installation authority. The only human instruction found for `epic_039`
explicitly requires an independent approval for every exact install, upgrade,
or implicit-pull binding. The later planning-role records repeatedly state that
no dependency was installed and that the real smoke checks remain outstanding.
There is no persisted `InstallationApproval` for either smoke dependency and no
separate `FeasibilityAuthorization` for the epic_034 adapter probe.

## Read-only environment observations

These commands cannot install, pull, create, or run anything and were therefore
safe to execute without installation approval.

| Observation | Command | Actual result |
| --- | --- | --- |
| Host Java | `java -version` | Amazon Corretto OpenJDK `11.0.26` (`11.0.26+4-LTS`) |
| Container engine | `docker version` | Docker client/server `28.0.0`, Linux `amd64` |
| Cached image inventory | `docker image ls --digests --no-trunc` | `structurizr/structurizr:2026.09.19-playwright` is already present at repo digest `sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c` and image ID `sha256:97681b22557abb2044ff2b67ae374956824c01da46b76be60858281adf678864` |
| Cached image metadata | `docker image inspect structurizr/structurizr@sha256:c89b...9644c` | Entrypoint `/usr/local/structurizr.sh`; declared `JAVA_HOME=/usr/lib/jvm/java-25-openjdk-amd64`; OCI base-image version label `24.04` |

The selected distribution is Structurizr `2026.09.19-playwright` from the
publisher's `structurizr/structurizr` Docker Hub repository. Structurizr's
[versioned binary documentation](https://docs.structurizr.com/binaries) says
the 2026.09.19 Java distribution requires Java 21 and identifies the
`2026.09.19-playwright` image as the Playwright-enabled Noble distribution.
The observed host Java 11 is therefore incompatible with that distribution's
host-Java requirement. The cached image metadata declares a bundled Java 25
location, but metadata is not an in-container runtime check; the bundled
runtime and Structurizr command still require an authorized real execution.

Image presence is also not evidence of an authorized pull. It predates this
attempt, and no approval provenance or pull attempt was found. The immutable
digest is recorded solely to make a future approval exact.

## Required approvals and remaining attempts

The following are blockers, not pre-approved recipes:

1. **Project-local install:** a human must select and approve one harmless
   dependency binding containing dependency ID, exact version, authoritative
   source, checksum, this actual environment identity, project-local scope and
   destination, exact install operation, exact verification operation, and
   cleanup. Those facts are not present, so no candidate command was run.
2. **Structurizr image operation:** independently approve dependency ID
   `structurizr_2026_09_19_playwright`, version `2026.09.19-playwright`, source
   `https://hub.docker.com/r/structurizr/structurizr`, digest
   `sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`,
   the observed Docker/Linux/amd64 environment, container-only scope, the exact
   digest-qualified run/check command, and removal of the created container and
   owned outputs. Approval must say whether using the already-cached image is
   allowed; any pull remains a separately guarded mutation.
3. **Adapter feasibility:** separately review and authorize a bounded
   epic_034 feasibility artifact, its input/output paths, environment, limits,
   operation, and cleanup. Installation/check success must not create this
   authority. The production adapter remains out of scope.

After those records exist, the trusted runner must recheck each binding and
current policy immediately before dispatch, append the actual attempts, verify
the digest and actual environment, record `java -version` and a harmless
Structurizr command inside the digest-qualified container, clean only owned
artifacts, and persist the adapter result independently.

## Deterministic integration coverage

Deterministic tests are contract evidence only; they do not turn this blocked
real-smoke record into a pass. The scoped suite covers:

- permitted project-local/container setup, read-only recheck, and independent
  feasibility;
- denial of implicit pull or unsafe system/default/sudo/license/credential
  mutation before executor dispatch;
- offline source, checksum mismatch, unsupported prompt, timeout, and wrong
  environment blockers;
- stale authority/completion, duplicate ping, interrupted partial setup, and
  restart reconciliation; and
- explicit empty-manifest planning without provider work, while separately
  scoped feasibility still gates non-empty scenarios.

The real local install, in-container runtime/check, and adapter-feasibility
acceptance remain open until their independently authorized attempts exist.
