# Running the workflow on Orca

Coordinator-only reference. Orca owns dispatching, messaging, waiting and worker lifecycle; this
file only maps the workflow onto Orca's mechanisms. Before the first command, resolve the Orca
executable as the installed `orchestration` skill instructs, then load its version-matched guide
(`<orca> skills get orchestration`, plus the `coordinator-loop`, `placement-and-remote`,
`messaging-and-gates` and, when something fails, `recovery-and-cleanup` references). The guide
is authoritative for flags, placement, lifecycle safety and recovery; where it differs from this
file on those, the guide wins. Model selection is the exception (see *Launch preferences*).
Examples below write `orca`.

## One run per task

`orca orchestration run-create --objective "<task>" --json` once; all dispatches belong to it.
Task and worker mutations only work in the run your session is bound to
(`orca orchestration run-use --id <run>` switches). Record every task and dispatch id you create.

## Launch preferences (model, effort)

The user who runs this workflow has authorized the coordinator to choose models and effort
(`roles/coordinator.md`, section 1), unless they restricted that choice. This replaces the
guide's default of passing `--model` only when the user named one; the guide still decides which
flags are supported.

`worker-start ... --agent <claude|codex|...> [--model <id> [--effort <level>]]`. Model ids are
the harness's own ids; `--effort` needs `--model`; neither combines with `--terminal`. Omit both
to use the harness default. Every start receipt has `launch.requested` and `launch.effective` -
record both in the observation log; effective `null` means the harness default applied. If a
requested model is rejected or not effective, record that and decide whether the default is
acceptable for the role before continuing.

## Dispatching a worker

Dispatch new work with `worker-start --spec`, which creates the task and its dispatch in one call
(no separate `task-create`, so no orphaned tasks). Retrying a failed task follows the guide
instead (`--task <task> --retry-of <dispatch>`), never a second `--spec` task for the same work.

1. Render the prompt: `python3 <skill-dir>/scripts/compose_prompt.py --role <role> --context <ctx.json> [--set KEY=VALUE ...] --out <prompt.md>`.
   It prints JSON with `prompt` and the validated `workspace`.
2. Start the worker **in exactly that workspace**:
   `orca orchestration worker-start --spec "$(cat <prompt.md>)" --task-title "<wp> <role>"
   --worktree path:<workspace> --agent <agent> [--model <id> --effort <level>] --json`
   (`--worktree current` is equivalent when the workspace is your own).
3. Record task id, dispatch id, role, requested/effective model and workspace.

If `worker-start` exits non-zero, do not relaunch blindly: read the receipt's `failedStage` and
`residualResources` and follow the guide's recovery reference. A task it created but never
started is closed as described under *Cleanup*.

**Shared workspace** - spec author, spec critic and reviewers work in your integration
worktree (critic and reviewers read-only).

**Independent workers** - create and verify their worktrees before anyone starts:

1. `orca worktree create --name <wp>-tests --base-branch <integration branch>
   --parent-worktree <selector of your worktree> --json` (same for `<wp>-impl`), without
   `--agent`; take the paths from the output.
2. Render each prompt with its own path as `workspace`, the integration commit as `baseline`,
   its sibling's path and branch in `isolation` and its writable paths in `ownership`.
   `compose_prompt.py` refuses the context unless the workspace is the worktree root and sits
   exactly on the baseline.

## Author/critic dialogue

Start both, then send each the other's address once:
`orca orchestration send --to dispatch:<author> --type status --subject "Peer" --body "Critic: dispatch:<critic>"`
(and vice versa). They exchange `status` messages directly and wait with `check --wait` on
their own terminal handle.

## Waiting and processing

- Wait with `orca orchestration check --wait --types worker_done,escalation,question
  --timeout-ms <ms> --json`, keeping the timeout below your shell's command timeout. A timeout
  is a checkpoint, not a failure; after several empty waits inspect
  `orca orchestration worker-list --run <run> --json`.
- `check --wait` writes keepalive lines to stderr every 15 s. Send stderr to a log in the run
  directory instead of the console: `orca orchestration check --wait ... --json
  2>>"<run>/logs/orca-stderr.log"`. Nothing is lost and the exit status stays intact; when the
  command fails, prints no JSON, or reports `ok: false`, read the end of that log.
- A delivery is the whole FIFO batch (including heartbeats and status messages) and is replayed
  until acknowledged: process every message, then `check --ack <delivery id>`. Heartbeat-only
  batches need an ack too.
- Answer questions with `orca orchestration reply --id <message id> --body "..."`. An
  `escalation` may be informational; acknowledge it with a message to its dispatch.

## Settling workers

On every `worker_done`, check outcome, files and report path against the assignment, then
**release** the worker (`orca orchestration worker-release --dispatch <id>`) before
acknowledging - unless you dispatch the same worker's immediate next step right now (below).
Do not retain workers for later phases: `worker-retain` is for user-requested debugging, and a
retained terminal is not guaranteed to still run its agent when you come back.

## Continuing a worker or starting a fresh one (revision, repair)

The default is a **fresh worker** of the same model family as the original author: create its
worktree from the integration branch (as for independent workers, name it e.g.
`<wp>-impl-repair`), and brief it through the context with the original worker's report, the
spec snapshot, the assigned findings and the integration commit as `baseline`.

Continue the same terminal only for an immediate follow-up within the same phase, and only if
`orca orchestration worker-list --run <run> --json` shows its `projection.liveness.verdict` as
`live`:

```
orca orchestration worker-start --spec "$(cat <prompt.md>)" --task-title "<wp> <role> repair" \
  --terminal <worker's terminal handle> --worktree path:<its worktree> --json
```

`worker-show --dispatch <id>` gives the terminal handle; model and effort stay as launched.
If this start fails, fall back to a fresh worker - never retry the same terminal blindly.

## Cleanup

After a package is accepted, and once more before the final report:

1. **Workers:** `orca orchestration worker-list --run <run> --terminal-state reclaimable --json`
   must be empty; release what it lists after checking each one's state (use the row's
   `projection.nextAction`).
2. **Tasks:** `orca orchestration task-list --run <run> --json` - every task you created must be
   `completed` or `failed`. Close a task that was never started or was abandoned with
   `orca orchestration task-update --id <task> --status failed --result "cancelled: <why>; superseded by <task>"`
   (stop or abandon its worker first if it has one). Only touch tasks of your own run whose ids
   you recorded; never delete or close tasks of other runs or workflows.
3. **Worktrees:** remove worker worktrees only after confirming each is clean and its branch is
   contained in the integration branch (`git merge-base --is-ancestor <branch> <integration
   branch>`), unless the user asked to keep them. `orca worktree rm --worktree path:<path>`
   returns immediately but removes the worktree asynchronously and deletes its branch as well;
   wait until `git worktree list` no longer shows it. Only if the branch still exists
   afterwards, delete it with `git branch -d <branch>` (`-d` refuses unmerged branches -
   investigate instead of forcing).
