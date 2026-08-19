---
name: orca-orchestrator
description: Orchestrate software-engineering work through Orca with spec-first planning, role-separated Junior/Senior execution, independent review, adaptive harness/model/locality routing, bounded autonomous recovery, and minimal project-owner intervention.
metadata:
  version: "0.7.0"
---

# Orca Orchestrator

Use this skill when coordinating non-trivial software-engineering work through Orca.

The primary objective is to minimize Project Owner intervention while preserving correctness, reviewability, scope discipline, and bounded resource use. Prefer autonomous execution and machine-to-machine feedback loops over asking the owner for routine implementation decisions, but never allow autonomy to become an unbounded loop.

See [CHANGELOG.md](CHANGELOG.md) for behavioral/schema changes across versions.

## Core principles

1. **Spec first.** Before implementation, make the task sufficiently precise that implementation and testing can proceed independently against the same frozen intent.
2. **Separate roles from levels.** Developer, Tester, and Reviewer are separate roles with separate contexts working only against the frozen spec; Junior/Senior is an orthogonal authority/cost level within each role. See [workflow.md](references/workflow.md#roles).
3. **Separate execution from judgment.** Junior workers perform bulk implementation, testing, exploration, and troubleshooting. Senior workers spend higher-cost judgment on planning, review, escalation, and takeover.
4. **Independent review.** A reviewer must not simply endorse the implementer. Prefer a different model and fresh context. When that is unavailable, use the defined review fallback rather than informal self-review.
5. **Iterate before escalating to the owner.** A Senior `RETURN` should normally create Junior rework, but only within configured recovery limits.
6. **Bound autonomous recovery.** Rework, specification repair, dispatches, blocking waits, and optional elapsed time have explicit limits. Do not silently exceed them.
7. **Verify takeover work.** `TAKE_OVER` changes who implements the task; it does not remove the need for verification.
8. **Route empirically, across model, harness, and locality.** Select harness, model, and local-vs-cloud execution using current task requirements plus learned state. Do not treat any combination as permanently best.
9. **Learn from outcomes.** Record completed execution/review cycles as observations. Distinguish raw observations, deterministic aggregates, and summarized beliefs.
10. **Keep mutable state outside the skill installation.** Skill updates must never overwrite learned state.

## Runtime paths

Resolve paths using XDG conventions:

- Config: `${XDG_CONFIG_HOME:-$HOME/.config}/orca-orchestrator/`
- State: `${XDG_STATE_HOME:-$HOME/.local/state}/orca-orchestrator/`

Do not assume the XDG environment variables are set.

## Before orchestrating

1. Inspect repository guidance (`AGENTS.md`, project docs, roadmap/specification files).
2. Read user configuration if present, including orchestration limits.
3. Read `capabilities.json` (what is available), `registry.json` (what is believed to perform well), deterministic aggregates, and recent relevant observations if present. These are distinct files with distinct write paths — see [state.md](references/state.md#paths).
4. Run `scripts/discover.py --write` if `capabilities.json` is stale or incomplete, or if the task may need a harness/backend/effort level not yet confirmed available. It reports local tool/backend availability and known cloud-harness auth signals; it does not enumerate cloud models or effort levels (see [routing.md](references/routing.md#discovery)).
5. Classify the task sufficiently for routing; avoid elaborate taxonomy when a simple classification is enough.
6. Create a frozen task specification for Developer, Tester, and Reviewer work (see [workflow.md](references/workflow.md#roles)).
7. Run `scripts/task.py start` before any dispatch, to snapshot task counters for dispatches, rework rounds, spec revisions, and elapsed time. Do not dispatch before this has run.

See:

- [workflow.md](references/workflow.md)
- [routing.md](references/routing.md)
- [guardrails.md](references/guardrails.md)
- [state.md](references/state.md)

## Default execution loop

Use the following loop unless the task clearly warrants a simpler path (see [workflow.md](references/workflow.md#roles) for the Developer/Tester/Reviewer role split):

1. **Plan/specify** the task and acceptance criteria; freeze the spec before Developer and Tester start.
2. **Select** Junior harness/model/locality for Developer and, separately, for Tester, based on evidence, task fit, cost, latency, and uncertainty.
3. **Dispatch** Developer and Tester in separate isolated contexts derived only from the frozen spec, each recorded with `scripts/task.py record --event dispatch`, provided task limits allow another dispatch. Neither receives the other's intermediate reasoning.
4. **Verify** that Developer and Tester actually ran relevant checks; do not rely solely on their completion reports. Record a `kind: execution` observation for each dispatch (Developer, Tester, Reviewer, rework, takeover) via `scripts/state.py observe --task-id <task_id> '{"kind":"execution", ...}'` as it finishes — one per dispatch, not one for the whole task (see [state.md](references/state.md#observation-schema)).
5. **Converge**: run the Tester's checks against the Developer's implementation. If either level disagrees within a role (e.g. a Senior Developer/Tester correction), treat that as an intra-role review round, not a separate escalation.
6. **Review** with a Senior Reviewer, independent of both Developer and Tester, against the frozen specification and actual repository state.
7. Interpret review as one of:
   - `APPROVE`: integrate/complete.
   - `RETURN`: create semantic rework with the findings included in the initial rework context, routed back to the role(s) responsible, if the rework budget remains.
   - `TAKE_OVER`: Senior finishes the task when Junior iteration is no longer efficient/reliable; verify the resulting work independently before completion.
   - `SPEC_DEFECT`: repair the specification only when intent can be recovered without inventing requirements; otherwise create an Owner gate.
8. After every `RETURN`, `SPEC_DEFECT`, technical retry, or takeover decision, use `scripts/task.py record` and `scripts/task.py status` to check configured limits before creating more work.
9. Before declaring the task complete, run `scripts/task.py finish` **first**, then record exactly one `kind: task` observation for the task's overall outcome via `scripts/state.py observe --task-id <task_id> '{"kind":"task", ...}'` — this order is required: `observe` rejects a `kind: task` observation for a task that isn't finished yet, and rejects a second one for a task that already has one. `--task-id` fills the dispatch/rework/spec-revision counters and termination reason from `task.py`'s own state; do not include those fields in the JSON body yourself, they are rejected if present. Completion is not reached until both have been invoked.
10. Ask the Project Owner only when a genuine gate remains or bounded autonomous recovery is exhausted and Senior takeover cannot safely finish the task.

## Communication rules

- Use Orca messaging for asynchronous coordination when delivery ordering is not critical.
- For blocking questions, use a mechanism that guarantees the worker receives the answer before continuing.
- Do not allow blocking communication to wait indefinitely. Apply the configured timeout and escalate according to [guardrails.md](references/guardrails.md).
- For `RETURN` findings, prefer a fresh rework task/dispatch whose initial context already contains the review findings instead of starting work and sending mandatory context afterward.
- Treat technical retries separately from semantic rework. Retry execution failures; create rework after a meaningful review result.

## Review independence

Follow the reviewer independence fallback order and takeover-closure verification defined in [guardrails.md](references/guardrails.md#reviewer-independence-fallback). Never treat an implementer's completion report or self-review as independent approval.

## Owner gates

Create an owner gate only when the missing decision materially changes intended behavior, scope, architecture, security posture, irreversible data handling, external commitments, or similarly consequential choices, or when configured autonomous-recovery limits are exhausted and no safe Senior completion path remains.

Do not gate on:

- routine code organization,
- test implementation details,
- reversible local decisions,
- choices that can be resolved from repository conventions,
- ordinary failure recovery that Junior/Senior iteration can still handle within policy.

## Adaptive routing

Do not hard-code statements such as "always use Pi" or "Qwen is best for coding". Harnesses, models, versions, and tool integrations evolve.

Prefer current evidence. Consider:

- task type and complexity,
- role (Developer/Tester/Reviewer) and level (Junior/Senior),
- need for tool use, long-context exploration, vision, or structured reasoning,
- local vs. cloud execution (privacy, latency, cost, availability) and, for cloud, effort/reasoning-budget level,
- observed autonomy and owner interventions,
- first-pass quality,
- rework success and number of review rounds,
- tool reliability and loop behavior,
- runtime/cost,
- harness/model/backend/locality/effort/version combination,
- confidence and age of the evidence.

For low-risk, well-specified tasks, occasionally explore under-tested viable combinations so the registry can improve instead of locking permanently onto early winners.

## State updates

Use the state helper scripts when available rather than manually rewriting structured state. Calling them is mandatory, not optional best practice:

- `scripts/task.py start` before the first dispatch of a task.
- `scripts/task.py record` after every dispatch, rework round, spec revision, technical retry, or blocking timeout.
- `scripts/state.py observe --task-id <task_id> '{"kind":"execution", ...}'` after each Developer/Tester/Reviewer/rework/takeover dispatch finishes.
- `scripts/task.py finish`, then `scripts/state.py observe --task-id <task_id> '{"kind":"task", ...}'`, in that order, before the task is reported complete.

A task is not complete if these calls were skipped, even if the underlying work is done. If you reach the end of a task and cannot recall calling them, call `scripts/task.py status` to check, and record the missing `kind: task` observation before finishing.

- Raw observations are append-only while active and preserved when archived.
- `aggregates.json` is a deterministic statistical view derived from active and archived observations.
- `registry.json` contains revisable routing beliefs and should remain traceable to evidence.
- Old observations may move to an archive to keep the regular loading path compact; compaction must not discard raw evidence.

Never modify this `SKILL.md` merely because one run performed badly. Update runtime observations instead.

## Scope discipline

The Orchestrator owns coordination, not unlimited implementation scope. Prevent:

- unrelated refactors,
- stale-document drift,
- test blindness between implementation and independently derived verification,
- fake-only validation where real behavior can be tested,
- accidental dependency/runtime leakage,
- unrecorded changes to reproducibility assumptions,
- unbounded review/rework or specification churn.

When repository-specific instructions conflict with this generic workflow, obey the repository-specific instructions unless doing so would violate an explicit owner requirement or a configured safety/resource guardrail.
