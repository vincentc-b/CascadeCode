# Draft feature brief: Recover Task provider write failures

## Intent

When a Task agent cannot write its assigned worktree, Cascade should identify the provider environment failure, repair a known safe setting, and resume the same Task. The owning Feature Team should see the cause and recovery result. A permissions failure must not become a misleading `no_task_changes` failure or consume repeated attempts that cannot succeed.

`task_026_004_002` exposed this gap. Its Codex SWE turn reached the Task worktree and passed tests, but `apply_patch` was refused by Codex's read-only sandbox. The Task was marked blocked as `no_task_changes`; retrying it with the same provider settings repeated the refusal. The Codex launcher now explicitly requests `workspace-write` for SWE turns, but this brief covers detection and recovery if a future launch, policy, or provider change removes write access again.

## Required behavior

1. Before a SWE turn, verify the assigned Task worktree and provider launch settings permit the scoped file writes needed by that turn. Keep planning roles under their current guarded tool permissions. Do not broaden access outside the assigned worktree.
2. Classify a provider sandbox or tool permission refusal as `provider_write_denied`, with the provider, attempted operation, and actionable cause. Do not present it as `no_task_changes` or treat passing tests on an unchanged tree as a deliverable.
3. The supervisor repairs a recognized safe launch configuration and resumes the existing Task branch, worktree, checkpoint, provider, model, and plan once. If a policy or filesystem permission cannot be safely repaired, retain the blocked Task with a precise reason and tell the Feature Team what needs operator action.
4. Give the owning Feature Team a scoped recovery request and status for its direct child Task. The parent can trigger the same supervised recovery operation used by the periodic health sweep; it cannot grant broad sandbox permissions or mutate another team's worktree.
5. Make recovery bounded and idempotent across restarts and concurrent parent requests. Preserve uncommitted files and normal test, commit, and merge gates.

## Acceptance scenarios

- A Codex SWE turn launched with a read-only sandbox is detected before work or on the first refused write, repaired to Task-scoped `workspace-write`, and resumed without a human Git edit.
- A rejected write never ends as `no_task_changes`, even if tests pass on the unchanged tree.
- A Feature Team sees the blocked reason and can request recovery of its own Task; a second request does not spawn another worker.
- A provider or machine policy that forbids writes remains blocked with a clear operator action. Recovery never selects unrestricted filesystem access.
- Planning turns retain guarded MCP access; unrelated operator and parent worktrees remain untouched.

## Implementation boundaries

Build on the Task execution lease, checkpoint, provider launcher, parent health sweep, and recovery operation planned in `epic_027`. The launch setting can be repaired automatically only when Cascade knows the exact safe scope. Keep generic filesystem and account permission changes outside automatic recovery.
