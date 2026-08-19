---
name: orca-orchestrator
description: Orchestrate software-engineering work through Orca with spec-first planning, Junior/Senior execution, independent review, adaptive harness/model routing, bounded autonomous recovery, and minimal project-owner intervention.
---

# Orca Orchestrator

Use this skill when coordinating non-trivial software-engineering work through Orca.

The primary objective is to minimize Project Owner intervention while preserving correctness, reviewability, scope discipline, and bounded resource use. Prefer autonomous execution and machine-to-machine feedback loops over asking the owner for routine implementation decisions, but never allow autonomy to become an unbounded loop.

## Core principles

1. **Spec first.** Before implementation, make the task sufficiently precise that implementation and testing can proceed independently against the same frozen intent.
2. **Separate execution from judgment.** Junior workers perform bulk implementation, testing, exploration, and troubleshooting. Senior workers spend higher-cost judgment on planning, review, escalation, and takeover.
3. **Independent review.** A reviewer must not simply endorse the implementer. Prefer a different model and fresh context. When that is unavailable, use the defined review fallback rather than informal self-review.
4. **Iterate before escalating to the owner.** A Senior `RETURN` should normally create Junior rework, but only within configured recovery limits.
5. **Bound autonomous recovery.** Rework, specification repair, dispatches, blocking waits, and optional elapsed time have explicit limits. Do not silently exceed them.
6. **Verify takeover work.** `TAKE_OVER` changes who implements the task; it does not remove the need for verification.
7. **Route empirically.** Select harness and model using current task requirements plus learned state. Do not treat any harness/model pairing as permanently best.
8. **Learn from outcomes.** Record completed execution/review cycles as observations. Distinguish raw observations, deterministic aggregates, and summarized beliefs.
9. **Keep mutable state outside the skill installation.** Skill updates must never overwrite learned state.

## Runtime paths

Resolve paths using XDG conventions:

- Config: `${XDG_CONFIG_HOME:-$HOME/.config}/orca-orchestrator/`
- State: `${XDG_STATE_HOME:-$HOME/.local/state}/orca-orchestrator/`

Do not assume the XDG environment variables are set.

## Before orchestrating

1. Inspect repository guidance (`AGENTS.md`, project docs, roadmap/specification files).
2. Read user configuration if present, including orchestration limits.
3. Read the current capability registry, deterministic aggregates, and recent relevant observations if present.
4. Discover available harnesses/models if the registry is stale or incomplete.
5. Classify the task sufficiently for routing; avoid elaborate taxonomy when a simple classification is enough.
6. Create a frozen task specification for implementation and independent test/review work.
7. Initialize task counters for dispatches, rework rounds, spec revisions, and elapsed time when configured.

See:

- [workflow.md](references/workflow.md)
- [routing.md](references/routing.md)
- [guardrails.md](references/guardrails.md)
- [state.md](references/state.md)

## Default execution loop

Use the following loop unless the task clearly warrants a simpler path:

1. **Plan/specify** the task and acceptance criteria.
2. **Select** a Junior harness/model based on evidence, task fit, cost, latency, and uncertainty.
3. **Dispatch** implementation in an isolated worktree/task context where appropriate, provided task limits allow another dispatch.
4. **Verify** that the Junior actually ran relevant tests/checks; do not rely solely on its completion report.
5. **Review** with a Senior worker against the frozen specification and actual repository state.
6. Interpret review as one of:
   - `APPROVE`: integrate/complete.
   - `RETURN`: create semantic rework with the findings included in the initial rework context, if the rework budget remains.
   - `TAKE_OVER`: Senior finishes the task when Junior iteration is no longer efficient/reliable; verify the resulting work independently before completion.
   - `SPEC_DEFECT`: repair the specification only when intent can be recovered without inventing requirements; otherwise create an Owner gate.
7. After every `RETURN`, `SPEC_DEFECT`, technical retry, or takeover decision, check configured limits before creating more work.
8. Record the outcome, guardrail termination reason if any, and noteworthy observations.
9. Ask the Project Owner only when a genuine gate remains or bounded autonomous recovery is exhausted and Senior takeover cannot safely finish the task.

## Communication rules

- Use Orca messaging for asynchronous coordination when delivery ordering is not critical.
- For blocking questions, use a mechanism that guarantees the worker receives the answer before continuing.
- Do not allow blocking communication to wait indefinitely. Apply the configured timeout and escalate according to [guardrails.md](references/guardrails.md).
- For `RETURN` findings, prefer a fresh rework task/dispatch whose initial context already contains the review findings instead of starting work and sending mandatory context afterward.
- Treat technical retries separately from semantic rework. Retry execution failures; create rework after a meaningful review result.

## Review independence

Prefer, in order:

1. different model + fresh review context,
2. same model + fresh isolated review context without the implementer's reasoning/self-justification,
3. for high-risk work, an additional independent verification step or Owner gate when sufficient independence cannot otherwise be established.

Never treat an implementer's completion report or self-review as independent approval.

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
- need for tool use, long-context exploration, vision, or structured reasoning,
- observed autonomy and owner interventions,
- first-pass quality,
- rework success and number of review rounds,
- tool reliability and loop behavior,
- runtime/cost,
- harness/model/backend/version combination,
- confidence and age of the evidence.

For low-risk, well-specified tasks, occasionally explore under-tested viable combinations so the registry can improve instead of locking permanently onto early winners.

## State updates

Use the state helper scripts when available rather than manually rewriting structured state.

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
