# Workflow

This reference defines the default orchestration lifecycle. Adapt it to repository-specific instructions and task size while respecting configured guardrails.

## Roles

- **Project Owner**: defines intent and resolves genuine gates. Should not be required for routine implementation choices.
- **Orchestrator**: decomposes work, routes workers, maintains counters/limits, records outcomes.
- **Planner/Architect**: sharpens intent into an executable specification when needed, before the pipeline roles below start.

Below the Orchestrator, the standard code-change pipeline is organized along two independent dimensions:

- **Role** (what domain of work): **Developer**, **Tester**, **Reviewer**. Each role gets its own isolated context and works only from the frozen specification and the actual repository state, never from another role's intermediate reasoning.
- **Level** (authority/cost, orthogonal to role): **Junior** by default makes a single bounded attempt at implementation, testing, or exploration and reports the concrete result or failure; **Senior** performs high-value judgment — difficult diagnosis, architecture correction, escalation, takeover, or an explicitly assigned troubleshooting dispatch — and is expected to iterate as deeply as that work requires. Any role can be staffed by either level. See [Junior execution contract](#junior-execution-contract).

`role` (Developer/Tester/Reviewer/Planner) and `task_type` ([routing.md](routing.md)'s `planning`/`implementation`/`testing`/`review`/`troubleshooting`/`research`/`mixed`) are different axes and are not meant to map one-to-one. `role` is *who is dispatched and in what capacity* — it is what execution/task observations record (see [state.md](state.md#observation-schema)) and is deliberately kept small and closed, because it drives context isolation and review independence, not classification. `task_type` is *what kind of work the task/dispatch is*, used for routing and aggregation, and stays open to whatever classification is useful. A Troubleshooter or Researcher dispatch outside the fixed Developer/Tester/Reviewer pipeline is a `task_type`, executed under whichever `role` fits the situation (often Developer) — it does not need its own role value.

```text
              Junior                         Senior
Developer     bulk implementation            architecture-sensitive
              against the frozen spec        implementation, takeover
Tester        derives checks from the        diagnoses hard-to-reproduce
              frozen spec, independent        failures, judges test adequacy
              of the implementation
Reviewer      —                              independent APPROVE / RETURN /
                                              TAKE_OVER / SPEC_DEFECT verdict
```

Reviewer is Senior by default (see [Reviewer selection](#reviewer-selection)); a Junior Reviewer pass is only a supplementary check, never the independent review of record.

### Role isolation

- Developer and Tester are dispatched into separate contexts from the same frozen specification. Neither receives the other's intermediate reasoning, diffs-in-progress, or self-justification before convergence.
- They converge at integration: the Tester's checks run against the Developer's actual implementation, and both are inspected together during Review.
- This isolation is what prevents test blindness: a Tester who has seen the implementation's reasoning tends to test what was built rather than what was specified.

### Junior and Senior coordination within a role

When a Senior corrects or extends a Junior's output *within the same role* (e.g. a Senior Developer fixing a Junior Developer's partial implementation, or a Senior Tester strengthening a Junior Tester's checks), treat that as an **intra-role review round**: it uses the same rework accounting as a cross-role `RETURN` (see [guardrails.md](guardrails.md)), but does not by itself satisfy the independent cross-role review requirement below.

### Final cross-role review

A dedicated **Reviewer** pass, independent of both Developer and Tester, remains required before `APPROVE` even when Developer/Senior and Tester/Senior already coordinated internally. Intra-role coordination improves the candidate; it is not a substitute for independent review.

## Junior execution contract

By default, a Junior dispatch is a single bounded attempt, not an open-ended session. This
is a Junior-level default, not a universal restriction on every worker: a Senior dispatch,
or any dispatch that explicitly assigns troubleshooting/debugging as the task, is expected
to iterate as deeply as that assigned work requires.

Give every dispatched worker — any role, either level — the explicit, self-contained
[worker-contract.md](worker-contract.md) as part of its initial context, with the
Orchestrator having filled in that dispatch's level and the current worker-completion call
(see [Worker completion mechanism](#worker-completion-mechanism)), so the worker can operate
correctly without reading this skill's other references or discovering either value itself.

For Junior dispatches specifically:

- The Junior receives a bounded task derived from the frozen spec and attempts it directly.
- By default, it must not perform open-ended debugging, prolonged diagnosis, or repeated
  speculative fixes, and must not broaden its own task, unless the dispatch explicitly
  assigns it a troubleshooting/debugging task.
- When implementation or validation fails, the Junior reports the concrete failure — what
  it tried, what happened, what it observed — and ends its dispatch there. Deciding what
  happens next (retry, rework, takeover, escalation) belongs to the Orchestrator or a
  Senior, not the Junior.

The intended loop is:

```text
frozen spec -> Junior attempt -> result/failure -> Senior evaluation -> targeted RETURN/new dispatch if needed
```

not:

```text
Junior -> implement -> debug indefinitely -> repeatedly mutate approach
```

Senior workers, and a role explicitly assigned a troubleshooting/debugging `task_type`, may
perform deeper iterative diagnosis when that diagnosis is the assigned work itself. A Junior
Developer or Tester dispatch does not get that latitude implicitly, but nothing here narrows
what a Senior or an explicitly-assigned Troubleshooter is expected to do.

### Worker completion mechanism

`worker-contract.md` requires every worker to terminate through a specific completion call,
but that call's exact name is a property of the installed Orca version, not something this
skill can hard-code — it has changed across Orca releases before (see the `orchestration`
skill's own discovery note). Resolve it once per orchestration session, before the first
dispatch:

1. Confirm the Orca CLI is reachable and get the version-matched orchestration guide (e.g.
   `ORCA skills get orchestration`, per that skill's own instructions).
2. Read the current completion-call name from that guide.
3. Substitute it into `[COMPLETION_CALL]` in every `worker-contract.md` copy handed to a
   dispatched worker for the rest of the session.

Do this once and reuse the resolved name; do not make each dispatched worker rediscover it,
and do not guess a name from memory or a cached copy of a stub — the whole point of
resolving it from the version-matched guide is that this name can change between Orca
releases.

### Detecting a stalled or looping Junior

A compliant Junior stops itself per the contract above. Treat the following as evidence
that a running or just-completed Junior dispatch is not making progress, whether or not it
stopped on its own:

- it repeats the same failing action (same command, same edit, same check) without a
  materially different result,
- its own completion report describes cycling through similar fixes rather than one bounded
  attempt,
- it is still running with no new information (no new file changes, no new check output)
  since the last observed state.

When this happens, stop the dispatch rather than letting it continue, and treat the result
as a failed Junior attempt feeding Senior evaluation — the same `RETURN`/rework/`TAKE_OVER`
decision point described under [Review outcomes](#review-outcomes), not permission for the
Junior to keep iterating. This is a judgment call made from the evidence above, not a count
against a separate invented threshold; the existing dispatch and rework limits in
[guardrails.md](guardrails.md#dispatch-and-task-budgets) already bound how many such cycles
a task can absorb before requiring Senior takeover or an Owner gate.

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

Developer and Tester share the specification, not each other's intermediate reasoning (see [Role isolation](#role-isolation)). They converge through integration and review.

Separate worktrees or equivalent isolated contexts are preferred for conflicting parallel changes, and are required between Developer and Tester whenever test blindness matters.

For implementation tasks, Developer and Tester are always separate dispatches with isolated
contexts derived from the same frozen specification, regardless of task size or perceived
risk. Do not collapse them into one dispatch, even for a small or low-risk change. The
purpose is not only to avoid test blindness: independently deriving an implementation and a
test suite from the same frozen spec, without either side seeing the other's reasoning, is
itself evidence that the spec was precise enough to implement against — a collapsed dispatch
cannot produce that evidence, because there is no independent second reading of the spec to
compare against.

A completion report is evidence about what a worker claims to have done, not proof that checks passed. Inspect actual repository state and test/check results before review.

## Review outcomes

### APPROVE

The implementation satisfies the specification and no blocking finding remains.

### RETURN

The implementation is directionally valid but requires changes. Create a semantic rework task with all blocking findings present in its initial context. Do not treat RETURN as a technical retry.

Count reviewed rework attempts. When the configured rework limit is reached, do not create another Junior rework round. Prefer Senior `TAKE_OVER` when intent remains clear; otherwise escalate only as required by the guardrails.

### TAKE_OVER

Use when another Junior cycle is unlikely to be efficient or reliable, for example after repeated non-progress, systematic tool failure, exhausted rework budget, or a change whose remaining work requires Senior judgment.

A takeover implementation is not self-approving. Follow [guardrails.md](guardrails.md#take_over-closure) for the required post-takeover verification steps.

### SPEC_DEFECT

Use when the frozen specification is contradictory, materially incomplete, or wrong for the repository state.

Repair autonomously only when the intended correction follows from repository facts, authoritative project documentation, or already owner-approved requirements. If repair would invent or choose product intent, create an Owner gate.

Count material spec revisions and respect the configured limit. Do not use `SPEC_DEFECT` to weaken requirements because implementation is difficult.

## Reviewer selection

Reviewer is a distinct role from Developer and Tester (see [Roles](#roles)); follow the fallback order in [guardrails.md](guardrails.md#reviewer-independence-fallback) when choosing who reviews. Never accept the implementer's own completion report as review.

## Retry versus rework

- **Retry**: execution failed technically before a meaningful result (crash, transient tool failure, infrastructure failure).
- **Rework**: a meaningful result was reviewed and needs semantic correction.

Do not use retries to hide review history. Both retries and rework dispatches still consume task-level dispatch/resource budgets.

**Dispatch accounting tracks resource use, not execution quality.** Record
`scripts/task.py record --event dispatch` when a worker is started/issued — the moment the
Orchestrator commits a slot of the task's dispatch budget — not when a task result becomes
available. This keeps `max_dispatches` a straightforward orchestration/resource guardrail
and avoids a race where several workers could be started before any of them is counted.

**Operator/environment maintenance still consumes a dispatch, but is never execution
evidence.** A harness or worker that fails during startup because it needs an operator
action — a required update, an interactive login, a permission grant, or other
machine-level maintenance — was still a worker start that consumed budget, so it is recorded
as an ordinary `dispatch` like any other. What it must **not** become is a signal about the
routed model/harness's task performance: it produced no meaningful attempt at the assigned
task, so treat it as described in
[guardrails.md](guardrails.md#operatorenvironment-maintenance) — do not record a
`technical_retry` or a `kind: execution` observation describing this attempt, surface the
needed maintenance to the Project Owner when it requires owner action, then dispatch the
originally intended work again once the environment is repaired. That later dispatch is a
new, separately-counted dispatch in its own right.

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
- every dispatch that reached task-related execution — Developer, Tester, Reviewer, rework, or takeover — has a corresponding `kind: execution` observation. The one explicit exception is a dispatch blocked by [operator/environment maintenance](guardrails.md#operatorenvironment-maintenance) before it could attempt the task: it still counted toward `max_dispatches`, but produced no execution to observe, so it gets no `kind: execution` observation.
- the task has been closed via `scripts/task.py finish` **before** its overall outcome and any guardrail termination reason are recorded as exactly one `kind: task` observation (see [state.md](state.md#observation-schema)) via `scripts/state.py observe --task-id <task_id> '...'` — `state.py` enforces this order and rejects a second `kind: task` observation for the same task.

Do not report a task complete before both `task.py finish` and the `kind: task` observation have actually run, in that order; a described-but-unrecorded outcome leaves the registry unable to learn from the task, and an outcome recorded on the wrong observation kind (e.g. task-level fields on an execution observation) corrupts the aggregates instead of merely missing them — `state.py` rejects that mixing rather than silently accepting it.
