# State Model

The skill keeps user configuration and learned runtime state outside the installed skill directory.

## Paths

Resolve with XDG fallbacks:

- config root: `${XDG_CONFIG_HOME:-$HOME/.config}/orca-orchestrator/`
- state root: `${XDG_STATE_HOME:-$HOME/.local/state}/orca-orchestrator/`

State layout:

```text
config root/
└── config.json

state root/
├── registry.json
├── capabilities.json
├── aggregates.json
├── observations.jsonl
├── tasks/
│   └── <task_id>.json
└── archive/
    └── observations-*.jsonl
```

The layers have different purposes:

- `config.json`: user policy and hard limits,
- `observations.jsonl`: active append-only empirical observations,
- `archive/`: preserved older raw observations removed from the regular loading path,
- `aggregates.json`: deterministic statistics derived from active + archived observations,
- `registry.json`: compact, revisable **routing beliefs** derived from evidence — subjective, evolves only from observations,
- `capabilities.json`: mechanical **capability snapshot** written by `scripts/discover.py --write` — objective, overwritten wholesale on every discovery run, not learned.

Do not conflate these last two. `registry.json` answers "what do we believe about how well X performs"; `capabilities.json` answers "what is currently installed/reachable". A stale `capabilities.json` means re-run discovery; a stale-feeling `registry.json` means gather more observations. Neither script writes the other's file.

## Task guardrail state

`tasks/<task_id>.json` is short-lived, per-task guardrail bookkeeping. It is distinct from raw observations, deterministic aggregates, and qualitative registry beliefs: it is not learned evidence and is not compacted or archived like observations.

Each file has `schema_version`, `task_id`, `started_at`, nullable `finished_at`, `status`, nullable `termination_reason`, a snapshot of the task's `limits` (including `blocking_wait_minutes`, snapshotted like the other limits so a later config edit cannot change the policy for an already-running task), nullable `blocking_started_at`, and `counters` for dispatches, rework rounds, specification revisions, technical retries, and blocking timeouts. Computed status also includes `elapsed_minutes`, `blocking_elapsed_minutes` (`null` when not currently blocked), and booleans indicating whether each bounded dispatch, rework, specification-revision, elapsed-time, or blocking-wait limit has been reached. A `null` limit has no ceiling.

Use the helper rather than editing these files directly:

```bash
python scripts/task.py start <task_id> [--limits-json '{"max_rework_rounds": 3}']
python scripts/task.py record <task_id> --event dispatch
python scripts/task.py status <task_id>
python scripts/task.py block-start <task_id>
python scripts/task.py block-clear <task_id>
python scripts/task.py finish <task_id> [--termination-reason dispatch_limit_reached]
```

`start` snapshots configured limits and is idempotent, `record` increments the selected counter on an active task, `status` reports counters and computed limit state, and `finish` closes the task with an optional termination reason.

Do not conflate aggregates with beliefs. A deterministic count such as `RETURN=4/12` is different from a qualitative belief such as "feedback incorporation appears reliable for small implementation tasks".

## Configuration

Default v0.2 configuration:

```json
{
  "schema_version": 1,
  "exploration": {
    "enabled": true
  },
  "limits": {
    "max_rework_rounds": 2,
    "max_spec_revisions": 1,
    "max_dispatches": 8,
    "max_elapsed_minutes": null,
    "blocking_wait_minutes": 15
  },
  "compaction": {
    "enabled": true,
    "max_active_observations_per_combination": 50,
    "archive_batch_size_per_combination": 25,
    "stale_after_days": 90
  }
}
```

The limits are task-level policy. A `null` elapsed-time limit means that no generic wall-clock ceiling is enforced. Rework and dispatch limits still bound autonomous recovery.

`init` may add newly introduced default keys that are missing from an existing compatible config, but must not overwrite explicit user values.

## Observation schema

Observations are immutable records. Every observation has a `kind`, and it is required:

- `kind: "execution"` — one worker's dispatch in one role (Developer, Tester, or Reviewer). Carries a well-defined `harness`/`model`/`backend`, because it describes what actually ran. A task with separate Developer/Tester/Reviewer dispatches (see [workflow.md](workflow.md#roles)) produces one execution observation per dispatch, not one per task.
- `kind: "task"` — the task's overall outcome, recorded once per task. No single `harness`/`model` applies to a task that may have used three different combinations across its roles, so this kind omits them and instead carries task-level fields: `owner_interventions`, final `review_verdict`, total `rework_rounds`, `takeover`, `termination_reason`.

Do not put task-level fields (`owner_interventions`, final `review_verdict`, total `rework_rounds`) on an execution observation, and do not put a `harness`/`model` on a task observation. Mixing them is exactly what makes aggregates uninterpretable: a combination's "review_verdicts" count would silently mix per-dispatch and per-task verdicts, and a task's total rework count could get attributed to whichever role happened to log it. `scripts/state.py` enforces the field split (see [Required fields](#required-fields)) and computes separate aggregate views for each kind (see [Deterministic aggregates](#deterministic-aggregates)).

Fields may be omitted when unknown, subject to the required-field minimum for the observation's kind.

`role` distinguishes `developer`/`tester`/`reviewer` execution observations (see [workflow.md](workflow.md#roles)); `level` (`junior`/`senior`) records who ran it but is not part of the aggregation key (see [Deterministic aggregates](#deterministic-aggregates)) to avoid fragmenting evidence too finely. `host` is `local` or `cloud`. `effort` records the requested reasoning/thinking-effort level for cloud harnesses that expose one; leave it `null` for harnesses/backends without a configurable effort dimension — do not invent a value. `effort` and `model_variant` are both part of the combination key: the same model/harness at a different effort level or quantization is treated as a different combination for routing purposes (see [routing.md](routing.md#locality-and-effort)).

Execution observation:

```json
{
  "schema_version": 1,
  "timestamp": "2026-08-19T08:00:00Z",
  "kind": "execution",
  "task_id": "task-2026-08-19-configurable-cost-backend",
  "task_type": "implementation",
  "role": "developer",
  "level": "junior",
  "harness": "pi",
  "harness_version": "0.84.2",
  "model": "qwen/qwen3-coder-next",
  "model_variant": "4bit",
  "backend": "lmstudio",
  "host": "local",
  "effort": null,
  "completed": true,
  "notes": [
    "Several generated tests called torch.allclose without asserting the result"
  ]
}
```

Task observation, **as stored** after `--task-id` filled in the derived fields (the JSON body you actually submit to `observe --task-id task-2026-08-19-configurable-cost-backend '...'` omits `dispatches`/`rework_rounds`/`spec_revisions`/`technical_retries`/`blocking_timeouts`/`termination_reason` entirely — see [Required fields](#required-fields)):

```json
{
  "schema_version": 1,
  "timestamp": "2026-08-19T08:05:00Z",
  "kind": "task",
  "task_id": "task-2026-08-19-configurable-cost-backend",
  "task_type": "implementation",
  "task_summary": "Implement configurable cost backend",
  "completed": true,
  "owner_interventions": 0,
  "review_verdict": "APPROVE",
  "dispatches": 3,
  "rework_rounds": 1,
  "spec_revisions": 0,
  "technical_retries": 0,
  "blocking_timeouts": 0,
  "takeover": false,
  "termination_reason": null,
  "notes": []
}
```

### Required fields

- `execution`: `task_id`, `role`, `harness`, `model`.
- `task`: `task_id`, `task_type`.

`task_id` links both kinds to the same task and to `tasks/<task_id>.json` (see [Task guardrail state](#task-guardrail-state)). A `task`-kind observation **requires** `--task-id <task_id>`; `scripts/state.py observe` rejects a bare `kind: "task"` observation without it, rejects it if the referenced task hasn't been started or hasn't been finished (`task.py finish` must run first), and rejects it if that task already has a recorded `task` observation (a task's outcome is recorded exactly once). `--task-id` fills `dispatches`, `rework_rounds`, `spec_revisions`, `technical_retries`, `blocking_timeouts`, and `termination_reason` from the task's own deterministic guardrail state — these six fields are **always** taken from `tasks/<task_id>.json`; supplying any of them explicitly in the JSON body is rejected outright rather than silently overridden, so the learned record cannot drift from what `task.py` actually counted. `--task-id` also works for `execution`-kind observations, where it only stamps `task_id` onto the observation (no task-derived counters apply to a single dispatch, and no started task is required).

`execution` and `task` observations also reject each other's exclusive fields: an `execution` observation cannot carry `owner_interventions`/`review_verdict`/`takeover`/any of the six task-derived fields, and a `task` observation cannot carry `role`/`harness`/`model`/`backend`/`host`/`effort`/`model_variant`/`harness_version`/`level`. This is enforced by `scripts/state.py`, not just documented — see `TASK_ONLY_FIELDS`/`EXECUTION_ONLY_FIELDS` in `scripts/state.py`.

`termination_reason` values are defined in [guardrails.md](guardrails.md#budget-exhaustion-record); reuse them verbatim here rather than inventing new spellings.

Do not fabricate missing metrics. Unknown is preferable to false precision.

### Migrating from pre-0.5.0 observations

Observations written before the 0.5.0 execution/task split have no `kind` field and may mix what are now task-only and execution-only fields on the same record. Reading such a record as-is under the current schema would silently misclassify it as `execution` and could leak task-level fields into combination aggregates — so `scripts/state.py` refuses to read any `observations.jsonl`/archived observations file containing a record without a valid `kind`; `observe`, `aggregate`, `compact`, and `show observations`/`show aggregates` all fail loudly on it instead of guessing.

If this happens: move the offending file out of `observations.jsonl`/`archive/` (or delete it if the history isn't worth keeping — it was never used for anything beyond aggregates you can also just lose), then re-run `init`. There is no automated migrator for the pre-split shape; a general one would have to guess which role/harness/model a given legacy record's task-level-looking fields actually belonged to, which isn't recoverable from the data itself.

## Deterministic aggregates

`aggregates.json` is rebuilt from both active and archived raw observations. `harnesses`, `models`, `combinations`, and `role_combinations` are derived **only from `kind: "execution"` observations** — a task observation has no single harness/model to attribute. `tasks` is derived **only from `kind: "task"` observations**. This split is what keeps a combination's stats from silently mixing per-dispatch execution outcomes with per-task outcomes; see [Observation schema](#observation-schema) for why that distinction matters.

- `harnesses`: keyed by harness.
- `models`: keyed by model.
- `combinations`: keyed by `harness|model|backend|effort|model_variant` (`unknown`/`none` placeholders for missing fields). This is "what configuration was actually run", independent of which role used it.
- `role_combinations`: keyed by `role|harness|model|backend|effort|model_variant`. Use this, not `combinations`, when the question is role-specific fitness (e.g. "is this combination a good Reviewer" vs. "is this combination good in general") — `combinations` deliberately mixes Developer/Tester/Reviewer evidence for the same configuration together.
- `tasks`: keyed by `task_type`, built from `kind: "task"` observations only — task-level completion rate, mean owner interventions, final-review-verdict distribution, mean total rework rounds, takeover rate, and termination-reason distribution.

Grouping by every plausible dimension at once (harness × model × backend × effort × variant × role × host) was deliberately avoided: it fragments evidence into buckets too sparse to be useful. `combinations` and `role_combinations` are the two projections that matter most in practice (what was run, and who used it); reason over raw observations directly (see [Evidence hierarchy](routing.md#evidence-hierarchy)) for finer-grained questions the precomputed aggregates don't answer, rather than adding another grouping dimension by default.

`host` is intentionally not part of any key: it correlates strongly with `backend` (e.g. `lmstudio` implies local) and with whether `effort` is set (cloud harnesses expose effort; local backends generally do not), so a separate `host` dimension would mostly duplicate information already carried by those two fields.

Useful metrics include:

- observation count,
- completed count and completion rate,
- total/mean observed owner interventions,
- review-verdict counts,
- total/mean observed rework rounds,
- takeover count,
- guardrail-termination counts,
- last observation time,
- count of observations inside the configured recency window.

Do not turn these metrics into a hidden magic score. Routing may reason over them together with task context and qualitative observations.

`stale_after_days` defines the deterministic recency window exposed by aggregates. Evidence outside that window is preserved and still available, but should generally influence current routing less strongly than recent evidence.

## Registry schema

The registry is a compact derived view that helps routing:

```json
{
  "schema_version": 1,
  "updated_at": "2026-08-19T08:00:00Z",
  "harnesses": {},
  "models": {},
  "combinations": {},
  "role_combinations": {}
}
```

`role_combinations` mirrors `aggregates.json`'s role-specific view (see [Deterministic aggregates](#deterministic-aggregates)): use it for beliefs like "strong Developer, weak Reviewer" that `combinations` alone cannot express.

Entries should summarize evidence rather than encode immutable rules. Recommended fields include:

- `strengths`: concise observed strengths,
- `weaknesses`: concise observed weaknesses,
- `confidence`: `unknown|low|medium|high`,
- `observations`: count of supporting observations,
- `last_observed_at`,
- `version` or version range when relevant.

Qualitative registry beliefs should remain traceable to supporting raw observations/aggregates. A registry belief must not rewrite or delete contradictory evidence.

## Capabilities schema

`capabilities.json` is written wholesale by `scripts/discover.py --write`; it is not hand-edited and not incrementally merged:

```json
{
  "schema_version": 1,
  "updated_at": "2026-08-19T08:00:00Z",
  "tools": {},
  "backends": {},
  "cloud": {}
}
```

`tools`, `backends`, and `cloud` mirror `discover.py`'s stdout output (see [routing.md](routing.md#discovery)): installed CLI availability/version, local backend model listings (e.g. LM Studio), and per-harness cloud-auth signal plus whether the harness is known to expose a configurable effort dimension. Each `--write` run fully replaces the prior snapshot with what was just observed — there is no history here; use `observations.jsonl` if you need history of what was actually used.

`capabilities.json` says what was locally detectable, not what is definitively reachable. The `cloud.<harness>.any_present` signal is a heuristic based on common API-key environment variables; a harness that authenticates through its own login flow (for example a CLI that stores an OAuth token in its own config file rather than an env var) can be fully usable in the cloud even when `any_present` is `false`. Treat a `false` signal as "unconfirmed", not "unavailable" — verify with a real dispatch when it matters, rather than routing away from a harness solely because this heuristic didn't find a key.

## Compaction

The active `observations.jsonl` should remain small enough to load recent relevant evidence without unbounded context growth.

Compaction is deterministic and script-driven:

1. Group active observations: `execution`-kind observations by their combination key (`harness|model|backend|effort|model_variant`), `task`-kind observations by `task|<task_type>`. The two kinds are never grouped together, mirroring how aggregates keep them separate.
2. When a group exceeds `max_active_observations_per_combination`, select the oldest observations in that group.
3. Archive at least `archive_batch_size_per_combination` observations (or enough to return under the active threshold, whichever is larger).
4. Write selected observations to `archive/observations-*.jsonl`.
5. Rewrite active `observations.jsonl` without those archived entries.
6. Rebuild `aggregates.json` from active + archived raw evidence.

Raw observations are never discarded by compaction. Archiving changes the normal loading path, not the evidence history.

Automatic compaction may run after `observe` when a threshold is exceeded. It must not depend on LLM interpretation.

## Helper commands

The state helper exposes the baseline operations:

```bash
python scripts/state.py init
python scripts/state.py observe '{"kind":"execution","task_id":"task-1","role":"developer","harness":"pi","model":"qwen/qwen3-coder-next"}'
python scripts/task.py finish task-1   # required before a "task"-kind observation
python scripts/state.py observe --task-id task-1 '{"kind":"task","task_type":"implementation","review_verdict":"APPROVE"}'
python scripts/state.py show observations
python scripts/state.py show aggregates
python scripts/state.py show registry
python scripts/state.py show capabilities
python scripts/state.py aggregate
python scripts/state.py compact
python scripts/discover.py --write
python scripts/state.py summary
python scripts/state.py summary --human
```

Prefer these helpers over free-form edits of structured state.

`summary` is read-only: it never writes config, registry, capabilities, observations, aggregates, or task state. By default it prints one deterministic JSON object to stdout (`--human` prints a short text report of the same information instead); every top-level key is always present, even when zero/empty/null. It reports:

- `schema_version`, `generated_at`.
- `tasks`: `active_count`/`finished_count` from `tasks/<task_id>.json`, and `active` — one `task.py status_value()`-shaped object per active task, sorted by `task_id`.
- `observations`: `execution`/`task`/`total` counts across active + archived observations, plus `active_file`/`archived` splitting active `observations.jsonl` from `archive/observations-*.jsonl`.
- `capabilities`: whether `capabilities.json` exists, its `updated_at`, and `age_minutes` since then (`null` if absent).
- `aggregates`: counts of tracked harnesses/models/combinations/role_combinations/task_types, rebuilt in-memory from `all_observations()` (not read from `aggregates.json`, so `summary` stays correct even if aggregates haven't been rebuilt).
- `role_combinations`: the full finalized bucket (same shape as `aggregates.json`'s `role_combinations`) for every combination with at least one execution observation.

## Mutation rules

- Append raw observations; do not rewrite their contents to fit a later belief.
- Compaction may move raw observations from active state into the archive, but must preserve them unchanged in meaning.
- Aggregates are deterministic derived data and may be rebuilt at any time.
- Registry summaries may be updated as evidence changes.
- Capabilities are deterministic derived data like aggregates, but from live discovery rather than history: `capabilities.json` may be wholesale overwritten by `discover.py --write` at any time, and must never be updated with routing beliefs — those belong in `registry.json`.
- Never store mutable state in the installed skill directory.
- Include `schema_version` in all structured state files.
- Do not silently discard state that uses a newer schema version.
- Prefer helper scripts for structured writes so validation, atomicity, locking, and migrations can improve without changing the skill contract.

## What not to encode

Do not turn a small number of observations into hard-coded universal conclusions such as:

- `pi is bad at testing`,
- `qwen-code is always the best harness`,
- `gemma is too slow for all work`.

Preserve the context of the observation and let routing weigh current evidence.
