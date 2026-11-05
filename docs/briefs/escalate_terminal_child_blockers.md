# Draft brief: Escalate terminal child blockers through the team hierarchy

## Intent

When a Task or Feature cannot continue through its normal recovery controls, its owning team should receive a concrete escalation and be able to choose the next scoped work item. A blocked team must still be able to report its findings upward. The Epic Team should be able to request follow-up work from a completed Feature Team when that team owns the relevant context, or create a new Feature when the change has a new scope. A human should not have to edit board state to keep the hierarchy moving.

`task_035_003_004` exposed the gap. Its implementation and tests remained in its worktree, but an edit to `docs/tasks/**` triggered `forbidden_commit_paths`. Cascade marked the Task terminal, classified the error as a permission refusal, and rejected both Feature Team retry and orphan recovery. The Feature became blocked through its child incident. The Feature Team corrected the canonical Task instructions and recorded a recovery decision, but its blocked status also prevented minting a replacement Task or proposing an Epic amendment. The valid code had no route back into delivery through the team hierarchy.

## Required behavior

1. On a terminal child failure, deliver a durable, deduplicated escalation to its direct parent. Include the failure class, denied operation and path when relevant, execution attempt, branch/worktree, preserved changes, test evidence, and the reason each recovery control was refused. Show the same evidence in the War Room. Do not label a scoped commit-path violation as a missing credential or suggest granting broader permissions.
2. Keep blocked teams able to inspect their children, post decisions, and escalate to their parent. A blocked status may gate delivery and new work admission, but it must not silence the team's recovery planning or prevent a scoped upward request. Distinguish a child-derived monitoring blocker from an open Epic amendment so each clears through its own lifecycle.
3. Give the owning Feature Team a supervised route to repair and continue its Task when the forbidden change can be removed safely. Recheck the current worktree, Task spec, provider settings, execution lease, and commit guard before redispatch. Preserve allowed uncommitted changes, use the existing Task identity and branch when safe, and rerun the normal tests, commit, and merge gates. If cancellation and a replacement Task are required, record why and retain a link to the failed Task and its recoverable work.
4. When Task recovery needs a change outside the Feature contract, let the Feature Team escalate a concrete request to its Epic Team even while blocked. The Epic Team can approve a revised Feature scope, ask the Feature Team for a new Task, or create a new Feature with explicit dependencies. Keep the original incident visible until the selected work actually clears it.
5. When the relevant Feature Team has completed, let the Epic Team send it a scoped update request and bring it back into an active planning state through an explicit, auditable transition. Preserve its completed delivery and review history. The team must acknowledge the new request, plan follow-up work, and publish it through normal review gates. If reopening would corrupt completed history, use a linked follow-up Feature owned by that team instead.
6. Make escalation and recovery idempotent across restarts and concurrent health sweeps. One incident should not create duplicate Tasks, Features, amendments, messages, or worker turns. Parent decisions should record the selected action and the evidence that makes it safe; unresolved or refused actions remain actionable rather than silently closing the blocker.

## Acceptance scenarios

- A Task changes `docs/tasks/**` alongside valid code. The commit guard rejects the board edit, retains the code, and escalates the exact path and safe recovery options to the Feature Team. The parent removes the forbidden diff through supervised recovery, redispatches the same Task, and receives one tested deliverable.
- The same terminal incident is observed after a restart and by a health sweep. The parent sees one escalation and one recovery decision; no duplicate worker or replacement Task starts.
- A blocked Feature can request an Epic scope decision. The Epic Team can create a dependent follow-up Feature or authorize a revised Task without manually clearing unrelated blockers.
- An Epic Team requests an update from a completed Feature Team. That team resumes planning or owns a linked follow-up Feature while the completed delivery and review remain intact.
- A true external permission refusal stays blocked with an operator action. Neither the team nor recovery path bypasses the commit guard or expands filesystem access.
- Cancelling and replacing a failed Task preserves its branch/worktree evidence until the replacement has incorporated or explicitly declined the recoverable changes.

## Implementation boundaries

Build on the existing Task recovery status, execution lease, worktree registry, direct-report health sweep, blockage provenance, board decisions, and Epic amendment workflow. Keep filesystem and Git mutations in supervised operations. Give teams scoped recovery and escalation tools rather than unrestricted board writes. The War Room should expose the incident, owner, selected action, and current outcome from durable state.
