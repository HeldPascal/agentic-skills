# Adaptive Routing

Routing chooses a harness/model/backend combination for a concrete execution step. Treat routing knowledge as empirical and revisable.

## Inputs

Consider only dimensions that materially affect the task:

- task type: planning, implementation, testing, review, troubleshooting, research, mixed,
- complexity/risk,
- expected repository exploration/context size,
- tool-use requirements,
- vision requirement,
- latency/cost constraints,
- current availability of harnesses/models/backends,
- current task guardrail state,
- relevant prior observations and deterministic aggregates.

Avoid overly detailed classifications when evidence is sparse.

## Evidence hierarchy

Prefer, in order:

1. recent observations for the same harness + model + similar task,
2. recent observations for the same combination on adjacent tasks,
3. combination-level deterministic aggregates,
4. harness-level or model-level observations/aggregates,
5. declared capabilities and static metadata,
6. exploratory choice when evidence is insufficient.

Do not infer a permanent global ranking from one task.

Raw observations explain *why* an aggregate or belief exists. Aggregates summarize measurable outcomes. Registry entries express revisable routing beliefs. Keep those layers distinct.

## Useful outcome dimensions

Track when available:

- completion,
- owner interventions,
- first-pass review verdict,
- blocking findings,
- rework success,
- number of rework rounds,
- takeover/escalation,
- guardrail termination reason,
- tool-call reliability,
- loops/repeated exploration,
- tests/checks actually executed,
- handoff quality,
- runtime and cost.

The primary optimization target is low Project Owner intervention. Quality and configured resource limits remain constraints, not things to trade away merely for autonomy.

## Combination effects

Harness and model performance may interact. Preserve combination-level evidence when possible instead of assuming:

`harness_quality + model_quality = combination_quality`

Record backend and relevant model variant as well when they can materially affect behavior.

## Confidence and recency

Use qualitative confidence:

- `unknown`: no meaningful observations,
- `low`: one/few observations, stale evidence, or evidence from a materially different version,
- `medium`: repeated consistent and reasonably recent evidence,
- `high`: broad, consistent, recent evidence across relevant tasks.

Prefer recent evidence over stale evidence. Deterministic aggregates expose a configurable `stale_after_days` window and recent-observation counts; use those as recency signals rather than inventing a precise quality score.

Confidence should decline when evidence becomes stale or major harness/model versions change. A version change does not automatically erase history, but it should reduce how strongly old evidence influences routing until new observations accumulate.

## Exploration

Avoid permanent lock-in. On low-risk, well-specified work, occasionally choose a viable under-tested combination when the expected downside is limited.

Do not explore aggressively on high-risk changes merely to gather data, and do not use exploration to bypass task budgets.

## Rework routing

A `RETURN` is a distinct decision point. The best first-pass worker may not be the best rework worker.

Prefer the same Junior when:

- findings are concrete,
- prior progress was good,
- the harness/model has shown useful feedback incorporation,
- the configured rework limit has not been reached.

Switch Junior or `TAKE_OVER` when:

- the worker repeats the same failure,
- tool integration is the blocker,
- review findings require capabilities the combination lacks,
- prior evidence suggests another combination handles feedback better,
- repeated cycles are more expensive than Senior completion,
- the rework budget is exhausted.

Never start another Junior rework round after `max_rework_rounds` is reached.

## Review routing

Prefer a Senior reviewer using a different model and fresh context from the implementer.

If no practical alternative model exists, a same-model reviewer may be used only in a fresh isolated context without the implementer's reasoning/self-justification. For high-risk tasks, insufficient independence requires another verification mechanism or an Owner gate.

Reviewer selection itself can learn from evidence. A model/harness combination that is strong at implementation is not automatically the best reviewer.

## Guardrail-aware routing

Before every new dispatch, consider remaining task budget. A locally cheap worker is not actually cheap if it repeatedly consumes rework or dispatch budget.

Evidence that a combination frequently ends in `rework_limit_reached`, `dispatch_limit_reached`, takeover, or owner intervention should reduce its attractiveness for similar tasks even if first-pass runtime is low.

Conversely, a slower combination can be preferable when it reliably reduces Senior rework and owner involvement.

## Baseline when evidence is sparse

When no strong evidence exists:

1. choose an available coding-oriented local/low-cost Junior for well-specified implementation/testing,
2. use a stronger Senior for independent review,
3. stay within configured task limits,
4. record the result,
5. let subsequent routing learn from actual outcomes.

This is a fallback, not a permanent model/harness preference.
