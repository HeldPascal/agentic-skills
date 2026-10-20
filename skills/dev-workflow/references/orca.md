# Running the workflow on Orca

Coordinator-only reference. Orca owns dispatching, messaging, waiting and worker lifecycle; this
file only maps the workflow onto Orca's mechanisms. Before the first command, resolve the Orca
executable as the installed `orchestration` skill instructs, then load its version-matched guide
(`<orca> skills get orchestration`, plus the `coordinator-loop`, `placement-and-remote` and
`messaging-and-gates` references). Where the guide differs from this file, the guide wins.
Examples below write `orca`. Pass `--model`/`--effort` only where the guide and the user's
setup allow launch preferences, and compare `launch.requested` with `launch.effective`.

## One run per task

`orca orchestration run-create --objective "<task>" --json` once; all dispatches belong to it.

## Shared-workspace workers (spec author, spec critic, reviewers)

They work in the coordinator's workspace (the critic and reviewers read-only):

1. Write the context JSON with `"workspace"` = your workspace and `"agent"` = the harness you
   will start (`claude`, `codex`, or `other`), then render the prompt:
   `python3 <skill-dir>/scripts/compose_prompt.py --role <role> --context <ctx.json> --out <prompt.md>`
2. `orca orchestration worker-start --spec "$(cat <prompt.md>)" --task-title "<wp> <role>"
   --worktree current --agent <agent> [--model <id> --effort <level>] --json`

## Independent workers (test author, implementer)

Create and verify the worktrees **before** any worker starts, so prompts carry the real paths
and nothing runs on a wrong base:

1. Create both worktrees without an agent:
   `orca worktree create --name <wp>-tests --base-branch <integration branch>
   --parent-worktree <selector of your worktree> --json` (same for `<wp>-impl`); take the paths from the
   output.
2. `python3 <skill-dir>/scripts/check_baseline.py --worktree <path> --expect <baseline commit>`
   for each. Fix any problem before continuing.
3. Render each prompt with its own path as `workspace`, its sibling's path and branch in
   `isolation`, and its writable paths in `ownership`.
4. Start each worker on its existing worktree:
   `orca orchestration worker-start --spec "$(cat <prompt.md>)" --task-title "<wp> <role>"
   --worktree path:<path> --agent <agent> [--model <id> --effort <level>] --json`

Record dispatch id, role, effective model and worktree in the observation log.

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
- A delivery is the whole FIFO batch (including heartbeats and status messages) and is replayed
  until acknowledged: process every message, then `check --ack <delivery id>`. Heartbeat-only
  batches need an ack too.
- Answer questions with `orca orchestration reply --id <message id> --body "..."`. An
  `escalation` may be informational; acknowledge it with a message to its dispatch.

## Settling workers

On every `worker_done`, check outcome, files and report path against the assignment, then decide
the terminal's next owner before acknowledging:

- **Authors** (spec author after the spec phase, test author and implementer after initial
  development): keep them for later revision or repair with
  `orca orchestration worker-retain --dispatch <id>` - this is the workflow's policy, so it
  counts as requested retention.
- **Judges** (spec critic, reviewers) and authors whose package is accepted:
  `orca orchestration worker-release --dispatch <id>`.

Then `check --ack <delivery id>`. When a package is accepted,
`orca orchestration worker-list --run <run> --terminal-state reclaimable --json` must be empty.

## Continuing a worker (revision, repair)

Fast-forward its worktree to the integration branch
(`git -C <path> merge --ff-only <integration branch>`), render the prompt in mode `repair` (or
`revision`), create a task for it and dispatch it to the same terminal:

```
orca orchestration task-create --spec "$(cat <prompt.md>)" --task-title "<wp> <role> repair" --json
orca orchestration worker-start --task <task id> --terminal <worker's terminal handle> \
  --worktree path:<path> --json
```

`worker-show --dispatch <id>` gives the terminal handle; model and effort stay as launched.
A **fresh** repair worker instead gets a new worktree from the integration branch
(`orca worktree create --name <wp>-<role>-repair --base-branch <integration branch> ...`) and a
normal `worker-start --worktree path:<path>`.

## Cleanup after a package is accepted

Release its workers, then remove its worker worktrees and their merged branches:
`orca worktree rm --worktree path:<path>` and `git branch -d <branch>` (`-d` refuses unmerged
branches - investigate instead of forcing). Keep them only if the user asked to.
