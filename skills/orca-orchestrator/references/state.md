# State Model

The skill keeps user configuration and learned runtime state outside the installed skill directory.

## Paths

Resolve with XDG fallbacks:

- config root: `${XDG_CONFIG_HOME:-$HOME/.config}/orca-orchestrator/`
- state root: `${XDG_STATE_HOME:-$HOME/.local/state}/orca-orchestrator/`

Suggested files:

```text
config root/
└── config.json

state root/
├── registry.json
└── observations.jsonl
```

`config.json` expresses user policy. `observations.jsonl` contains append-only empirical observations. `registry.json` contains summarized, revisable beliefs derived from observations.

## Configuration

v0.1 keeps configuration intentionally small:

```json
{
  "schema_version": 1,
  "exploration": {
    "enabled": true
  }
}
```

Future versions may add policy constraints, permitted backends, cost budgets, routing preferences, or host metadata.

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
  "rework_rounds": 0,
  "rework_success": null,
  "takeover": false,
  "notes": [
    "Several generated tests called torch.allclose without asserting the result"
  ]
}
```

Do not fabricate missing metrics. Unknown is preferable to false precision.

## Registry schema

The registry is a compact derived view that helps routing. v0.1 may be maintained conservatively by the orchestrator or a helper script.

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

## Mutation rules

- Append raw observations; do not rewrite history to fit a later belief.
- Registry summaries may be updated as evidence changes.
- Never store mutable state in the installed skill directory.
- Include `schema_version` in all structured state files.
- Do not silently discard state that uses a newer schema version.
- Prefer helper scripts for structured writes so validation and atomicity can improve without changing the skill contract.

## What not to encode

Do not turn a small number of observations into hard-coded universal conclusions such as:

- `pi is bad at testing`,
- `qwen-code is always the best harness`,
- `gemma is too slow for all work`.

Preserve the context of the observation and let routing weigh current evidence.
