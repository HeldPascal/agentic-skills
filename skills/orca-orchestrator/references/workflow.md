# Workflow

This reference defines the default orchestration lifecycle. Adapt it to repository-specific instructions and task size while respecting configured guardrails.

## Roles

- **Project Owner**: defines intent and resolves genuine gates. Should not be required for routine implementation choices.
- **Orchestrator**: decomposes work, routes workers, maintains counters/limits, records outcomes.
- **Planner/Architect**: sharpens intent into an executable specification when needed.
- **Junior**: performs bulk exploration, implementation, testing, and troubleshooting.
- **Senior**: performs high-value judgment: review, difficult diagnosis, architecture correction, escalation, or takeover.

Junior/Senior is an authority/cost dimension, not a separate domain taxonomy. A Developer, Test-Developer, Planner, or Troubleshooter can be executed by either level when appropriate.

## Spec-first flow

Before parallel implementation/testing work, freeze enough of the specification to make independent work meaningful. Include:

- current behavior relevant to the change,
- required behavior,
- invariants/backward-compatibility expectations,
- scope constraints,
- acceptance criteria,
- expected verification.

Avoid prescribing implementation details unless they are themselves requirements.

Track material specification revisions. A clerical wording fix that does not alter intent need not count as a spec revision; a change to required behavior or acceptance criteria does.

## Independent implementation and verification

For changes where test blindness matters, implementation and independent test derivation should share the specification, not each other's intermediate reasoning. They may later converge through integration and review.

Separate worktrees or equivalent isolated contexts are preferred for conflicting parallel changes.

A completion report is evidence about what a worker claims to have done, not proof that checks passed. Inspect actual repository state and test/check results before review.

## Review outcomes

### APPROVE

The implementation satisfies the specification and no blocking finding remains.

### RETURN

The implementation is directionally valid but requires changes. Create a semantic rework task with all blocking findings present in its initial context. Do not treat RETURN as a technical retry.

Count reviewed rework attempts. When the configured rework limit is reached, do not create another Junior rework round. Prefer Senior `TAKE_OVER` when intent remains clear; otherwise escalate only as required by the guardrails.

### TAKE_OVER

Use when another Junior cycle is unlikely to be efficient or reliable, for example after repeated non-progress, systematic tool failure, exhausted rework budget, or a change whose remaining work requires Senior judgment.

A takeover implementation is not self-approving. After the Senior changes the repository:

1. execute the relevant verification/checks,
2. compare the resulting state against the frozen specification,
3. obtain a fresh independent review when practical,
4. for high-risk work, require sufficiently independent verification before completion.

### SPEC_DEFECT

Use when the frozen specification is contradictory, materially incomplete, or wrong for the repository state.

Repair autonomously only when the intended correction follows from repository facts, authoritative project documentation, or already owner-approved requirements. If repair would invent or choose product intent, create an Owner gate.

Count material spec revisions and respect the configured limit. Do not use `SPEC_DEFECT` to weaken requirements because implementation is difficult.

## Reviewer selection

Prefer a reviewer with a different model and a fresh execution context.

If another practical model is unavailable, use the same model only in a fresh isolated review context that receives the frozen specification and repository state but not the implementer's reasoning or self-justification.

For high-risk work where sufficient independence cannot be established, require another verification mechanism or an Owner gate. Never accept the implementer's own completion report as review.

## Retry versus rework

- **Retry**: execution failed technically before a meaningful result (crash, transient tool failure, infrastructure failure).
- **Rework**: a meaningful result was reviewed and needs semantic correction.

Do not use retries to hide review history. Both retries and rework dispatches still consume task-level dispatch/resource budgets.

## Blocking communication

Blocking questions must have a bounded wait. When the configured timeout is reached:

- technical/repository-resolvable questions should escalate to the Orchestrator or Senior,
- owner-intent/scope questions should become an Owner gate,
- stale work should be cancelled or replaced if the answer would no longer be useful.

A timeout is not permission to invent missing intent.

## Task-level limits

Before creating a new dispatch after failure, review, spec repair, or takeover, check the configured limits in [guardrails.md](guardrails.md).

`scripts/task.py` provides the deterministic `start`, `record`, and `status` counters referenced here.

At minimum track:

- dispatch count,
- Junior rework rounds,
- material spec revisions,
- blocking wait duration when relevant,
- elapsed task time when an elapsed-time limit is configured.

When a hard limit is reached, do not silently continue. Prefer a safe Senior completion path if one already exists; otherwise create the minimum necessary Owner gate and record the termination reason.

## Owner escalation

Escalate only when autonomous resolution would require inventing intent or when bounded autonomous recovery is exhausted and no safe Senior completion path remains. Typical gates include:

- choosing between materially different product behaviors,
- expanding or reducing agreed scope,
- architecture decisions with significant long-term consequences,
- security/privacy/data-retention choices,
- irreversible migrations or destructive actions,
- external commitments.

Before escalating, summarize viable options, consequences, current guardrail state, and the minimum decision needed.

## Completion

A workflow is complete when:

- acceptance criteria are met,
- relevant checks/tests were actually executed or the reason they could not be was explicitly captured,
- independent review is `APPROVE` or an explicitly justified equivalent verification condition applies,
- takeover work, if any, received post-takeover verification,
- the final repository state is understandable,
- the outcome and any guardrail termination reason have been recorded for future routing.
