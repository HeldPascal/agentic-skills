# Guardrails

This reference defines bounded autonomy for the orchestration loop. The goal is to minimize Project Owner intervention without allowing unbounded retries, rework, specification churn, or resource use.

## Default limits

Unless user configuration overrides them, use these conservative defaults:

```json
{
  "max_rework_rounds": 2,
  "max_spec_revisions": 1,
  "max_dispatches": 8,
  "max_elapsed_minutes": null,
  "blocking_wait_minutes": 15
}
```

A `null` elapsed-time limit means no generic wall-clock ceiling is enforced. Different local and cloud workers can vary substantially in latency, so rework and dispatch limits are the primary v0.2 termination guards.

Limits are task-level policy, not suggestions. Do not silently exceed them.

## Rework termination

A `RETURN` normally creates semantic rework for the Junior. Count each reviewed rework attempt as one rework round, regardless of which role (Developer or Tester) receives it.

An intra-role Senior correction of a Junior's output (see [workflow.md](workflow.md#junior-and-senior-coordination-within-a-role)) also counts as a rework round: it consumes the same bounded budget even though it never leaves the role.

Use `scripts/task.py record --event rework` to persist each round and `scripts/task.py status` to check the snapshotted limit deterministically.

When `max_rework_rounds` is reached:

1. Do not start another Junior rework round.
2. Prefer Senior `TAKE_OVER` if the remaining intent is clear and the Senior can complete the task autonomously.
3. Create an Owner gate only when autonomous completion would require inventing product intent, changing scope, or making another consequential owner-level decision.

Repeated technical failures are not rework rounds, but they still count toward task dispatch/resource limits.

## Operator/environment maintenance

Distinguish a harness/environment that cannot start from a worker that attempted the task
and produced a poor result. Examples of the former: a required software update, an
interactive login/re-authentication, a missing permission grant, a license/quota block, or
other machine-level maintenance the Orchestrator cannot perform itself.

A worker that was started/issued and then blocked on maintenance during startup was still a
dispatch — see [workflow.md](workflow.md#retry-versus-rework): `max_dispatches` tracks
resource use (how many workers were started), which is a different question from whether
that worker's attempt says anything about the routed model/harness's task performance. This
section is only about the latter.

1. Record the `dispatch` as usual (it consumed a worker start and a slot of `max_dispatches`
   like any other), but do not record a `technical_retry` or a `kind: execution` observation
   attributing the failure to the routed model/harness — no task-related execution
   happened, so there is nothing to say about that combination's performance.
2. This does not need its own persistent guardrail counter or limit: there is no
   `max_environment_maintenance_events`, and none is being proposed. Maintenance-blocked
   starts are already indirectly bounded, since each one still consumes a dispatch (step 1)
   and so counts toward `max_dispatches` like any other; a dedicated counter would only
   duplicate that. The two things that do carry concrete value already have a place:
   - if resolving the blocker requires owner action, the Owner gate itself is the record
     (step 4 below),
   - if the retry dispatch issued after repair (step 5) succeeds, a short note in *that*
     dispatch's `kind: execution` observation `notes` (e.g. "a prior dispatch needed a
     harness update before this attempt could start") preserves the context without a
     dedicated field.
3. If the Orchestrator can resolve the blocker itself (e.g. a routine, non-destructive
   update it is already permitted to run), do so and then dispatch normally.
4. If resolving it requires an owner-level action (credentials, interactive login,
   permissions, purchasing/licensing), create an Owner gate describing exactly what
   maintenance is needed — this is a genuine gate, not routine implementation.
5. Once the environment is repaired, dispatch the originally intended work again. This is a
   new, separately-counted `dispatch` against `max_dispatches` — the blocked attempt already
   consumed its own dispatch count in step 1, and this retry consumes another.
6. If maintenance cannot be completed and no alternative route exists, finish the task with
   `termination_reason: environment_maintenance_required` (see
   [Budget exhaustion record](#budget-exhaustion-record)) rather than reporting the
   model/harness as incapable of the task.

## Reviewer independence fallback

Prefer a reviewer that differs from the implementer in both model identity and execution context.

Fallback order:

1. Different model, fresh review context.
2. Same model, fresh dispatch/context, with only the frozen specification and repository state required for review. Do not provide the implementer's chain of reasoning or self-justification.
3. For high-risk work where sufficient independent judgment cannot be established, require an additional independent verification step or an Owner gate.

Never treat the implementer's own completion report as independent review.

## TAKE_OVER closure

`TAKE_OVER` changes who implements the remaining work; it does not waive verification.

After a Senior modifies the implementation:

1. Run the relevant tests/checks or capture why they cannot be run.
2. Verify the resulting repository state against the frozen specification.
3. Prefer a fresh independent reviewer when practical.
4. A Senior must not simply self-approve its own takeover implementation without an independent verification step.

For low-risk changes where another reviewer is unavailable, an explicit verification pass in a fresh context may serve as the completion condition. For high-risk changes, use a second independent reviewer or Owner gate.

## SPEC_DEFECT handling

A specification defect exists when the frozen specification is contradictory, materially incomplete, or factually wrong for the repository state.

The Orchestrator or Planner may repair the specification autonomously when the correction is derivable from:

- repository facts,
- existing owner-approved scope,
- authoritative project documentation,
- previously established requirements.

Create an Owner gate when repairing the specification would require choosing or inventing product intent, materially changing scope, architecture, security posture, irreversible data behavior, or another consequential requirement.

Count autonomous specification repairs. After `max_spec_revisions` is reached, another material specification defect requires an Owner gate unless the new defect is purely clerical and does not alter intent.

Use `scripts/task.py record --event spec_revision` to persist material revisions and `scripts/task.py status` to check the limit.

Do not use `SPEC_DEFECT` to move requirements merely because implementation is difficult.

## Dispatch and task budgets

Track task-level resource use when possible.

`scripts/task.py record` persists dispatch and related counters, and `scripts/task.py status` computes counter and elapsed-time limit status instead of relying on LLM self-tracking.

At minimum count dispatches created for the task, including Developer, Tester, Reviewer, rework, takeover, and technical retry dispatches, regardless of role. `max_dispatches` is a single task-level budget shared across roles, not a separate budget per role. When `max_dispatches` is reached, stop creating new dispatches and choose one of:

- complete using an already-running worker if no new dispatch is required,
- Senior takeover within an existing eligible context,
- Owner gate with a concise status and options.

If `max_elapsed_minutes` is configured, treat it as an additional hard ceiling measured from orchestration start. Do not fake precise elapsed-time accounting when the runtime cannot provide it reliably.

A stalled or looping Junior dispatch (see [workflow.md](workflow.md#detecting-a-stalled-or-looping-junior)) does not get a separate numeric threshold: stopping it and escalating to Senior evaluation draws on these same dispatch/rework counters, since a stopped attempt followed by a new dispatch or rework round is exactly what those counters already bound.

Future versions may add token or monetary budgets when those metrics are reliably available from the selected providers.

## Blocking communication timeout

When a worker is blocked waiting for an answer, do not wait indefinitely.

`blocking_wait_minutes` is snapshotted into the task at `task.py start` like the other limits, so it cannot silently change mid-task if config is edited later. Call `scripts/task.py block-start <task_id>` when a block begins and `scripts/task.py status <task_id>` to check `blocking_elapsed_minutes`/`limit_reached.blocking_wait_minutes` deterministically, instead of estimating elapsed wait time yourself.

After `blocking_wait_minutes` (`limit_reached.blocking_wait_minutes` is `true`):

- route technical or repository-resolvable questions to a Senior or Orchestrator capable of answering them,
- route owner-intent or consequential scope questions to an Owner gate,
- cancel or replace stale blocked work when the answer is no longer useful,
- record the resolution with `scripts/task.py record --event blocking_timeout`, which also clears the blocking-wait marker.

If the worker is unblocked before the limit is reached, call `scripts/task.py block-clear <task_id>` instead — this does not count as a timeout and does not increment `blocking_timeouts`.

A timeout is an escalation trigger, not permission to invent missing intent.

## Budget exhaustion record

When any guardrail terminates autonomous recovery, record the reason in the task outcome/observation. Useful reasons include:

- `rework_limit_reached`,
- `spec_revision_limit_reached`,
- `dispatch_limit_reached`,
- `elapsed_time_limit_reached`,
- `blocking_timeout`,
- `independent_review_unavailable`,
- `environment_maintenance_required` (see [Operator/environment maintenance](#operatorenvironment-maintenance) — the task ended because required maintenance could not be completed, not because a worker performed poorly).

These observations are routing evidence: repeated exhaustion with a harness/model combination can justify different future routing without hard-coding universal conclusions.
