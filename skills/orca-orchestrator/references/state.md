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
├── aggregates.json
├── observations.jsonl
└── archive/
    └── observations-*.jsonl
```

The layers have different purposes:

- `config.json`: user policy and hard limits,
- `observations.jsonl`: active append-only empirical observations,
- `archive/`: preserved older raw observations removed from the regular loading path,
- `aggregates.json`: deterministic statistics derived from active + archived observations,
- `registry.json`: compact, revisable routing beliefs derived from evidence.

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

Observations are immutable records. Fields may be omitted when unknown.

```json
{
  "schema_version": 1,
  "timestamp": "2026-08-19T08:00:00Z",
  "task_type": "implementation",
  "task_summary": "Implement configurable cost backend",
  "harness": "pi",
  "harness_version": "0.84.2",
  "model": "qwen/qwen3-coder-next",
  "model_variant": "4bit",
  "backend": "lmstudio",
  "host": "local",
  "completed": true,
  "owner_interventions": 0,
  "review_verdict": "RETURN",
  "blocking_findings": 2,
  "dispatches": 2,
  "rework_rounds": 0,
  "rework_success": null,
  "takeover": false,
  "termination_reason": null,
  "notes": [
    "Several generated tests called torch.allclose without asserting the result"
  ]
}
```

Useful `termination_reason` values include:

- `rework_limit_reached`,
- `spec_revision_limit_reached`,
- `dispatch_limit_reached`,
- `elapsed_time_limit_reached`,
- `blocking_timeout`,
- `independent_review_unavailable`.

Do not fabricate missing metrics. Unknown is preferable to false precision.

## Deterministic aggregates

`aggregates.json` is rebuilt from both active and archived raw observations. It should contain auditable statistics grouped by:

- harness,
- model,
- harness/model/backend combination.

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
  "combinations": {}
}
```

Entries should summarize evidence rather than encode immutable rules. Recommended fields include:

- `strengths`: concise observed strengths,
- `weaknesses`: concise observed weaknesses,
- `confidence`: `unknown|low|medium|high`,
- `observations`: count of supporting observations,
- `last_observed_at`,
- `version` or version range when relevant.

Qualitative registry beliefs should remain traceable to supporting raw observations/aggregates. A registry belief must not rewrite or delete contradictory evidence.

## Compaction

The active `observations.jsonl` should remain small enough to load recent relevant evidence without unbounded context growth.

Compaction is deterministic and script-driven:

1. Group active observations by harness/model/backend combination.
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
python scripts/state.py observe '{"task_type":"implementation","harness":"pi","model":"qwen/qwen3-coder-next"}'
python scripts/state.py show observations
python scripts/state.py show aggregates
python scripts/state.py show registry
python scripts/state.py aggregate
python scripts/state.py compact
```

Prefer these helpers over free-form edits of structured state.

## Mutation rules

- Append raw observations; do not rewrite their contents to fit a later belief.
- Compaction may move raw observations from active state into the archive, but must preserve them unchanged in meaning.
- Aggregates are deterministic derived data and may be rebuilt at any time.
- Registry summaries may be updated as evidence changes.
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
