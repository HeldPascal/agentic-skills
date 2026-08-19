# Workflow

This reference defines the default orchestration lifecycle. Adapt it to repository-specific instructions and task size.

## Roles

- **Project Owner**: defines intent and resolves genuine gates. Should not be required for routine implementation choices.
- **Orchestrator**: decomposes work, routes workers, maintains the loop, records outcomes.
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

## Independent implementation and verification

For changes where test blindness matters, implementation and independent test derivation should share the specification, not each other's intermediate reasoning. They may later converge through integration and review.

Separate worktrees or equivalent isolated contexts are preferred for conflicting parallel changes.

## Review outcomes

### APPROVE

The implementation satisfies the specification and no blocking finding remains.

### RETURN

The implementation is directionally valid but requires changes. Create a semantic rework task with all blocking findings present in its initial context. Do not treat RETURN as a technical retry.

### TAKE_OVER

Use when another Junior cycle is unlikely to be efficient or reliable, for example after repeated non-progress, systematic tool failure, or a change whose remaining work requires Senior judgment.

### SPEC_DEFECT

Use when the frozen specification is contradictory, materially incomplete, or wrong. Repair/specify before judging implementation against it.

## Retry versus rework

- **Retry**: execution failed technically before a meaningful result (crash, transient tool failure, infrastructure failure).
- **Rework**: a meaningful result was reviewed and needs semantic correction.

Do not use retries to hide review history.

## Owner escalation

Escalate only when autonomous resolution would require inventing intent. Typical gates include:

- choosing between materially different product behaviors,
- expanding or reducing agreed scope,
- architecture decisions with significant long-term consequences,
- security/privacy/data-retention choices,
- irreversible migrations or destructive actions,
- external commitments.

Before escalating, summarize viable options, consequences, and the minimum decision needed.

## Completion

A workflow is complete when:

- acceptance criteria are met,
- relevant checks/tests were actually executed or the reason they could not be was explicitly captured,
- Senior review is APPROVE or an equivalent justified completion condition applies,
- the final repository state is understandable,
- the outcome has been recorded for future routing.
