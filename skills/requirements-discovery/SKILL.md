---
name: requirements-discovery
description: Turn a vague feature idea, bug report or development goal into a clear, testable task through focused interactive questions - producing a Task Brief and a lightweight Decision Record. Use at the start of non-trivial development work when requirements, scope or important trade-offs are not yet clear, before writing specifications or code.
metadata:
  version: "0.1.0"
---

# Requirements discovery

Transform the user's request into a task that can proceed to a testable specification without
unresolved, blocking product decisions. Do not try to remove every uncertainty.

## 1. Do your homework first

Before asking anything:

1. Inspect the repository: README, docs, roadmaps, architecture notes, ADRs, existing specs,
   relevant code and tests.
2. Check the repository state you are working from: is your branch/worktree based on the
   branch that actually contains the latest plans? (A worktree created from a stale remote ref
   can miss the very documents that define the task.)
3. Separate what is **already decided** (documents, prior user statements) from what is
   **missing and material** to the implementation.

## 2. Ask only what the user must decide

- Ask about product behavior, scope, user-visible trade-offs and priorities - not about
  implementation details you can reasonably decide or leave to the specification process.
- Prefer structured questions (single choice, multiple choice) with a recommended option and
  a one-line consequence per option; group related questions; keep rounds small.
- Free-text answers often refine or reject the offered options. Read them carefully, reflect
  your interpretation back when it changes the plan, and ask again only if it is still unclear.
- You may propose a decomposition into work packages here; confirm it with the user when it
  shapes the plan.

## 3. Produce the outputs

Write them to the agreed location. Default to a private working directory outside the
repository; put them into the repository only if the user or project conventions want that -
some projects must not receive such documents. Ask when unclear. One file with two sections is
fine.

**Task Brief**

- Objective and motivation
- Expected observable behavior
- Scope and explicit non-goals
- Relevant technical and architectural constraints
- High-level acceptance goals
- Assumptions
- Remaining non-blocking uncertainties

**Decision Record** - only significant user decisions, each with:

- the decision and its rationale (in the user's terms),
- rejected alternatives where they clarify intent,
- what it implies for later work (e.g. "therefore an added system must reuse existing results").

Keep it lightweight; routine choices do not need an entry. Later explicit user decisions
supersede earlier ones - record the change rather than editing history away.

## 4. Hand-off

Downstream work treats the outputs as authoritative intent:

`current user decisions and project constraints -> Task Brief / Decision Record -> specification -> tests and implementation`

Others may challenge a decision and propose alternatives, but must not silently override it.
Discovery is re-entered whenever later work reveals missing or contradictory requirements.
