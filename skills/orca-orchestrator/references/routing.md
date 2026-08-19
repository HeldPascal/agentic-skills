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
- relevant prior observations.

Avoid overly detailed classifications when evidence is sparse.

## Evidence hierarchy

Prefer, in order:

1. recent observations for the same harness + model + similar task,
2. observations for the same combination on adjacent tasks,
3. harness-level or model-level observations,
4. declared capabilities and static metadata,
5. exploratory choice when evidence is insufficient.

Do not infer a permanent global ranking from one task.

## Useful outcome dimensions

Track when available:

- completion,
- owner interventions,
- first-pass review verdict,
- blocking findings,
- rework success,
- number of rework rounds,
- takeover/escalation,
- tool-call reliability,
- loops/repeated exploration,
- tests/checks actually executed,
- handoff quality,
- runtime and cost.

The primary optimization target is low Project Owner intervention. Quality remains a constraint, not something to trade away merely for autonomy.

## Combination effects

Harness and model performance may interact. Preserve combination-level evidence when possible instead of assuming:

`harness_quality + model_quality = combination_quality`

Record backend and relevant model variant as well when they can materially affect behavior.

## Confidence

Use qualitative confidence in v0.1:

- `unknown`: no meaningful observations,
- `low`: one/few observations or old evidence,
- `medium`: repeated consistent evidence,
- `high`: broad and recent evidence across relevant tasks.

Confidence should decline when evidence becomes stale or major harness/model versions change.

## Exploration

Avoid permanent lock-in. On low-risk, well-specified work, occasionally choose a viable under-tested combination when the expected downside is limited.

Do not explore aggressively on high-risk changes merely to gather data.

## Rework routing

A RETURN is a distinct decision point. The best first-pass worker may not be the best rework worker.

Prefer the same Junior when:

- findings are concrete,
- prior progress was good,
- the harness/model has shown useful feedback incorporation.

Switch Junior or TAKE_OVER when:

- the worker repeats the same failure,
- tool integration is the blocker,
- review findings require capabilities the combination lacks,
- repeated cycles are more expensive than Senior completion.

## Baseline when evidence is sparse

When no strong evidence exists:

1. choose an available coding-oriented local/low-cost Junior for well-specified implementation/testing,
2. use a stronger Senior for independent review,
3. record the result,
4. let subsequent routing learn from actual outcomes.

This is a fallback, not a permanent model/harness preference.
