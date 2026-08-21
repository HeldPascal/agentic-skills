# Changelog

All notable changes to the `orca-orchestrator` skill are documented here. This skill's `version` (in `SKILL.md` frontmatter) follows [Semantic Versioning](https://semver.org/): additive changes bump the minor version and clarifications/fixes bump the patch version, at any version. Before `1.0.0`, breaking changes to the state/config schema or the skill's behavioral contract also bump the minor version — semver's own pre-1.0 convention, where the public contract is still being established and every version may change it; from `1.0.0` onward, breaking changes bump the major version instead.

## 0.8.1

- Clarified startup lifecycle in `SKILL.md`: `scripts/state.py init` is now the explicit first mandatory step in [Before orchestrating](SKILL.md#before-orchestrating), run before reading `capabilities.json`, `registry.json`, aggregates, observations, or starting any task — on every orchestration session, not as a one-time or operator-run setup step. `init` was already idempotent (it creates state on a first run and only fills in newly introduced default keys otherwise, never resetting or deleting existing observations, registry beliefs, aggregates, capabilities, or task history); this only makes the ordering explicit in the workflow text. No behavioral change to `scripts/state.py`.

## 0.8.0

Addresses gaps exposed by the first real orchestration run against the Junior/Senior execution model.

- **Behavioral contract:** removed the "collapse Developer and Tester for small/low-risk tasks" escape hatch in [workflow.md](references/workflow.md#independent-implementation-and-verification). Developer and Tester are now always separate dispatches with isolated contexts derived from the same frozen spec for implementation tasks, regardless of size or perceived risk — independent implementation and test derivation is itself evidence that the frozen spec was precise, not only a defense against test blindness.
- **Behavioral contract:** a Junior dispatch defaults to a single bounded attempt, not an open-ended session. By default a Junior must not perform open-ended debugging, prolonged diagnosis, or repeated speculative fixes, and must not broaden its own task, unless the dispatch explicitly assigns troubleshooting/debugging; on failure it reports the concrete result and ends the dispatch, leaving the next decision to the Orchestrator/Senior. This is a Junior default, not a restriction on Senior or explicitly-assigned troubleshooting dispatches, which retain latitude for deeper iterative diagnosis. See [workflow.md#junior-execution-contract](references/workflow.md#junior-execution-contract). Core principle 3 in `SKILL.md` and the Roles description in `workflow.md` were reworded to match — Junior no longer lists "troubleshooting" as a default duty.
- Added [references/worker-contract.md](references/worker-contract.md): a small, explicit, self-contained completion contract to include in every worker's dispatch context (scope discipline, a single-pass default for Junior dispatches with explicit Senior/troubleshooting latitude, report-and-stop on failure, and always terminating through Orca's worker completion call). The Orchestrator resolves the dispatch's level and the exact current completion call name (from the installed Orca version's own orchestration guide) once per session and fills both into the contract text before dispatch, rather than leaving either for the worker to determine. See [workflow.md#worker-completion-mechanism](references/workflow.md#worker-completion-mechanism).
- Added guidance for detecting a stalled or looping Junior (repeating a failing action, a completion report describing cycling fixes, or no new progress) and stopping that dispatch to route into Senior evaluation instead of letting it continue — deliberately reusing the existing dispatch/rework counters rather than inventing a new numeric retry threshold. See [workflow.md#detecting-a-stalled-or-looping-junior](references/workflow.md#detecting-a-stalled-or-looping-junior).
- Distinguished operator/environment maintenance (a harness/environment that cannot start without an update, login, permission grant, or other machine-level fix) from task-related execution failure and from semantic rework, while keeping dispatch accounting a pure resource guardrail: a worker start/issued dispatch still consumes `max_dispatches` even when it then fails to start on a maintenance blocker, avoiding a race where several workers could be started before any of them is counted. What changes is execution evidence, not dispatch counting — a maintenance-blocked attempt gets no `technical_retry` and no `kind: execution` observation describing model/harness task performance, surfaces to the Project Owner when it needs owner action, and is followed by a new, separately-counted dispatch once the environment is repaired. This does not get its own guardrail counter or limit — a maintenance-blocked start already consumes a dispatch and so is already indirectly bounded by `max_dispatches`, so a dedicated counter would only duplicate that; the record lives in the Owner gate (when owner action is needed) or as a note on the retry dispatch's `kind: execution` observation. See [guardrails.md#operatorenvironment-maintenance](references/guardrails.md#operatorenvironment-maintenance).

## 0.7.0

- Added `scripts/state.py summary` (`--human` for text, JSON by default): a deterministic, read-only snapshot of active/finished tasks, execution/task observation counts (active + archived), capabilities freshness, and in-memory-rebuilt aggregate counts including full `role_combinations` buckets. Never writes any state file. See [state.md](references/state.md#helper-commands).

## 0.6.1

- Reading `observations.jsonl`/archived observation files now rejects any record without a valid `kind` (`execution`/`task`) instead of silently defaulting it to `execution`. Pre-0.5.0 observations had no `kind` and could carry now-task-only fields; letting them default to `execution` would have leaked those fields into combination aggregates. See [state.md](references/state.md#migrating-from-pre-050-observations) for what to do if this triggers.
- `execution` observations now reject a `task_id` in the JSON body that doesn't match `--task-id`, matching the check `task` observations already had.

## 0.6.0

0.5.0 documented the execution/task observation split but did not actually enforce it in code, so an agent could still put task-level fields on an execution observation, override task.py's counters by hand, record a task's outcome without `task.py` ever having run, or record it twice. `scripts/state.py` now enforces all of this mechanically:

- **Breaking:** `execution` observations reject task-only fields (`owner_interventions`, `review_verdict`, `takeover`, and the six task-derived counter/termination fields); `task` observations reject execution-only fields (`role`, `level`, `harness`, `harness_version`, `model`, `model_variant`, `backend`, `host`, `effort`).
- **Breaking:** `kind: "task"` now requires `--task-id`; `dispatches`/`rework_rounds`/`spec_revisions`/`technical_retries`/`blocking_timeouts`/`termination_reason` are always taken from `tasks/<task_id>.json` and rejected outright if supplied in the JSON body (previously `setdefault`, which let a caller-provided value silently win over the deterministic count).
- **Breaking:** a `kind: "task"` observation is rejected unless the referenced task exists, is finished (`task.py finish` must run first), and doesn't already have a recorded task observation — a task's outcome can now only be recorded exactly once, in the correct order.
- `task.py finish` now rejects finishing an already-finished task instead of silently overwriting `finished_at`/`termination_reason`.

## 0.5.0

Addresses external review feedback on 0.4.0 (state/observation semantics, aggregation granularity, and a spec-compliance issue).

- **Breaking:** observations now require `kind: "execution"` (one worker's dispatch in one role; needs `task_id`/`role`/`harness`/`model`) or `kind: "task"` (a task's one-time overall outcome; needs `task_id`/`task_type`). Previously a single observation shape conflated per-dispatch and per-task fields, so a task with three differently-routed roles (Developer/Tester/Reviewer) had no well-defined way to be recorded, and task-level fields like `owner_interventions`/`review_verdict` risked being triple-counted across roles.
- `scripts/state.py observe --task-id <task_id>` fills a `kind: "task"` observation's dispatch/rework/spec-revision/retry/blocking-timeout counters and termination reason from `tasks/<task_id>.json` instead of having them retyped, so the learned record can no longer drift from what `task.py` actually counted.
- `aggregates.json` gained `role_combinations` (keyed `role|harness|model|backend|effort|model_variant`) and `tasks` (keyed by `task_type`, from `kind: "task"` observations only); `combinations`/`harnesses`/`models` are now built only from `kind: "execution"` observations. `registry.json` gained a matching `role_combinations` section. The combination key also gained `model_variant` (was tracked as a field but never grouped on).
- **Breaking:** moved `version` out of `SKILL.md`'s top-level frontmatter into `metadata.version`, matching the [Agent Skills specification](https://github.com/agentskills/agentskills) (there is no top-level `version` field); verified with `skills-ref validate`.
- `blocking_wait_minutes` is now snapshotted into task state at `task.py start` like the other limits, with new `task.py block-start`/`block-clear` commands and a `blocking_elapsed_minutes`/`limit_reached.blocking_wait_minutes` computed in `status`, instead of being an unenforced config value.
- Replaced `discover.py`'s hardcoded per-harness effort-level enumeration (already stale) with a boolean `effort_configurable` signal; specific level names are a model/provider property that changes too fast for a baked-in list to track.
- Softened `capabilities.json` documentation: a `false` cloud-auth signal means "unconfirmed", not "unavailable" — some harnesses authenticate via their own login flow rather than an environment variable.
- Clarified that `role` (Developer/Tester/Reviewer/Planner) and `task_type` (planning/implementation/testing/review/troubleshooting/research/mixed) are independent axes, not meant to map one-to-one.
- Added a GitHub Actions workflow running `pytest` and `skills-ref validate` on push/PR.

## 0.4.0

- Split `registry.json` (revisable routing beliefs) from a new `capabilities.json` (mechanical snapshot written wholesale by `discover.py --write`); nothing wrote to `registry.json` automatically before, and the two had been conflated under "capability registry" language.
- Removed cross-file duplication of the reviewer-independence fallback order, `TAKE_OVER` closure steps, and `termination_reason` list: `guardrails.md` is now the single source, `SKILL.md`/`workflow.md`/`routing.md`/`state.md` reference it instead of restating it.
- Added tests for `discover.py` and `doctor.py`, which previously had no coverage.

## 0.3.0

- Split execution into separate Developer/Tester/Reviewer roles (orthogonal to Junior/Senior level), with isolated contexts and an explicit intra-role vs. cross-role review distinction.
- Added `role`, `host`, and `effort` as explicit observation/routing dimensions; the combination key used for aggregates/registry grouping is now `harness|model|backend|effort` instead of `harness|model|backend`.
- Made `discover.py` report a heuristic cloud-auth signal and known effort levels per harness, in addition to local tool/backend discovery, and documented discovery cadence.
- Made calling `task.py`/`state.py` at task start/record/finish a hard requirement in the workflow text, not a soft recommendation.
- Trimmed the repository README to a skill index; removed the skill-specific repository layout tree from it.

## 0.2.0

- Added `scripts/task.py` for deterministic per-task guardrail counters (dispatches, rework rounds, spec revisions, technical retries, blocking timeouts), replacing LLM self-tracking of limits.
- Added deterministic observation compaction/archiving and rebuildable aggregates in `scripts/state.py`.
- Documented bounded-autonomy guardrails (rework/spec/dispatch/elapsed-time limits, reviewer independence fallback, `TAKE_OVER` closure).

## 0.1.0

- Initial skill: spec-first workflow, Junior/Senior execution and review loop, adaptive harness/model routing, XDG-based config/state layout, local capability discovery, and the `state.py` helper (`init`/`observe`/`show`/`aggregate`).
