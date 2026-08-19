---
name: orca-orchestrator
description: Orchestrate software-engineering work through Orca with spec-first planning, Junior/Senior execution, independent review, adaptive harness/model routing, and minimal project-owner intervention.
---

# Orca Orchestrator

Use this skill when coordinating non-trivial software-engineering work through Orca.

The primary objective is to minimize Project Owner intervention while preserving correctness, reviewability, and scope discipline. Prefer autonomous execution and machine-to-machine feedback loops over asking the owner for routine implementation decisions.

## Core principles

1. **Spec first.** Before implementation, make the task sufficiently precise that implementation and testing can proceed independently against the same frozen intent.
2. **Separate execution from judgment.** Junior workers perform bulk implementation, testing, exploration, and troubleshooting. Senior workers spend higher-cost judgment on planning, review, escalation, and takeover.
3. **Independent review.** A reviewer must not simply endorse the implementer. Prefer a different model from the implementation worker when practical.
4. **Iterate before escalating to the owner.** A Senior `RETURN` should normally create a rework cycle for the Junior. Escalate to the owner only for genuine product/scope/architecture gates or when autonomous recovery is exhausted.
5. **Route empirically.** Select harness and model using current task requirements plus learned state. Do not treat any harness/model pairing as permanently best.
6. **Learn from outcomes.** Record completed execution/review cycles as observations. Distinguish raw observations from summarized beliefs.
7. **Keep mutable state outside the skill installation.** Skill updates must never overwrite learned state.

## Runtime paths

Resolve paths using XDG conventions:

- Config: `${XDG_CONFIG_HOME:-$HOME/.config}/orca-orchestrator/`
- State: `${XDG_STATE_HOME:-$HOME/.local/state}/orca-orchestrator/`

Do not assume the XDG environment variables are set.

## Before orchestrating

1. Inspect repository guidance (`AGENTS.md`, project docs, roadmap/specification files).
2. Read user configuration if present.
3. Read the current capability registry and recent relevant observations if present.
4. Discover available harnesses/models if the registry is stale or incomplete.
5. Classify the task sufficiently for routing; avoid elaborate taxonomy when a simple classification is enough.
6. Create a frozen task specification for implementation and independent test/review work.

See:

- [workflow.md](references/workflow.md)
- [routing.md](references/routing.md)
- [state.md](references/state.md)

## Default execution loop

Use the following loop unless the task clearly warrants a simpler path:

1. **Plan/specify** the task and acceptance criteria.
2. **Select** a Junior harness/model based on evidence, task fit, cost, latency, and uncertainty.
3. **Dispatch** implementation in an isolated worktree/task context where appropriate.
4. **Verify** that the Junior actually ran relevant tests/checks; do not rely solely on its completion report.
5. **Review** with a Senior worker against the frozen specification and actual repository state.
6. Interpret review as one of:
   - `APPROVE`: integrate/complete.
   - `RETURN`: create semantic rework with the findings included in the initial rework context.
   - `TAKE_OVER`: Senior finishes the task when Junior iteration is no longer efficient/reliable.
   - `SPEC_DEFECT`: repair the specification at the appropriate layer before continuing.
7. Repeat review/rework as justified.
8. Record the outcome and noteworthy observations.
9. Ask the Project Owner only when a genuine gate remains.

## Communication rules

- Use Orca messaging for asynchronous coordination when delivery ordering is not critical.
- For blocking questions, use a mechanism that guarantees the worker receives the answer before continuing.
- For `RETURN` findings, prefer a fresh rework task/dispatch whose initial context already contains the review findings instead of starting work and sending mandatory context afterward.
- Treat technical retries separately from semantic rework. Retry execution failures; create rework after a meaningful review result.

## Owner gates

Create an owner gate only when the missing decision materially changes intended behavior, scope, architecture, security posture, irreversible data handling, external commitments, or similarly consequential choices.

Do not gate on:

- routine code organization,
- test implementation details,
- reversible local decisions,
- choices that can be resolved from repository conventions,
- ordinary failure recovery that Junior/Senior iteration can handle.

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

Raw observations should be append-only. Summaries/registry entries are derived beliefs and may change as evidence accumulates.

Never modify this `SKILL.md` merely because one run performed badly. Update runtime observations instead.

## Scope discipline

The Orchestrator owns coordination, not unlimited implementation scope. Prevent:

- unrelated refactors,
- stale-document drift,
- test blindness between implementation and independently derived verification,
- fake-only validation where real behavior can be tested,
- accidental dependency/runtime leakage,
- unrecorded changes to reproducibility assumptions.

When repository-specific instructions conflict with this generic workflow, obey the repository-specific instructions unless doing so would violate an explicit owner requirement.
