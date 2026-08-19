# Adaptive Routing

Routing chooses a role, level, harness/model/backend combination, locality, and (for cloud) effort level for a concrete execution step. Treat routing knowledge as empirical and revisable.

## Inputs

Consider only dimensions that materially affect the task:

- task type: planning, implementation, testing, review, troubleshooting, research, mixed,
- role: Developer, Tester, or Reviewer (see [workflow.md](workflow.md#roles)),
- complexity/risk,
- expected repository exploration/context size,
- tool-use requirements,
- vision requirement,
- latency/cost constraints,
- locality (local vs. cloud) and, for cloud, effort/reasoning-budget level,
- current availability of harnesses/models/backends (see [Discovery](#discovery)),
- current task guardrail state,
- relevant prior observations and deterministic aggregates.

Avoid overly detailed classifications when evidence is sparse.

## Discovery

`scripts/discover.py` reports what can actually be observed locally: installed harness CLIs and their versions, models currently served by a local LM Studio backend, and — for harnesses with a known cloud mode — a heuristic cloud-auth signal (presence of common API-key environment variables) plus a static table of known effort/reasoning levels.

It deliberately does **not** enumerate which cloud models an account/key can reach, and cannot discover effort levels dynamically: cloud providers do not expose a generic "list models and effort levels for this key" endpoint, and effort is a request-time parameter rather than a queryable model property. Keep `KNOWN_EFFORT_LEVELS` in `discover.py` in sync with current provider documentation instead of trying to probe it.

Run `scripts/discover.py --write`:

- at orchestration start when `capabilities.json` is stale or missing entries for harnesses/backends the task may need,
- again mid-task only if a specific capability (a backend, a cloud harness, an effort level) turns out to be required and its availability was not already confirmed.

`--write` persists the result to `capabilities.json` (see [state.md](state.md#capabilities-schema)), overwriting the prior snapshot; it never touches `registry.json`. Do not re-run discovery on a fixed schedule inside a single task; it does not change fast enough within one task's lifetime to justify that.

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

## Locality and effort

Local and cloud execution are a routing dimension, not a proxy for Junior/Senior. A local model can be the right Senior reviewer for a low-risk, well-understood change if evidence supports it; a cheap, low-effort cloud call can be the right Junior implementer. Do not hard-code "Junior = local, Senior = cloud" — route on evidence and task fit instead, using locality/cost/latency/privacy as explicit inputs:

- **Local**: no per-token cost, no network dependency, but bounded by locally available model quality/context and hardware throughput. Prefer for high-volume, well-specified Junior work when local quality evidence is adequate.
- **Cloud**: typically stronger frontier models and configurable effort/reasoning budget, at per-call cost and latency, and with data leaving the local environment. Prefer for tasks needing capability beyond what local models demonstrate, or where effort can be tuned to the risk of the step (e.g. higher effort for Review/TAKE_OVER than for routine Junior implementation).

Treat effort level like `model_variant`: the combination key includes it (see [state.md](state.md#deterministic-aggregates)), so evidence at one effort level does not automatically transfer to another. When evidence for a given effort level is sparse, prefer the evidence hierarchy's fallback tiers (harness/model-level aggregates, then exploratory choice) over guessing an effort level with no supporting evidence.

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

Independence requirements for the Reviewer role are defined in [guardrails.md](guardrails.md#reviewer-independence-fallback); this section is only about which combination to route to within that constraint.

Reviewer selection can learn from evidence like any other role. A model/harness combination that is strong at implementation is not automatically the best reviewer. `aggregates.json` groups by harness/model/backend/effort only, not by role, so when reasoning about reviewer fitness, weight raw observations that carry `role: reviewer` (see [state.md](state.md#observation-schema)) more heavily than the combination-level aggregate, which mixes all roles together.

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
