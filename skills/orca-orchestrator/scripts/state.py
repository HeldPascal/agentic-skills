#!/usr/bin/env python3
"""State helper for the orca-orchestrator skill.

Supports:
- init: initialize config/state files with conservative defaults
- observe: append one immutable JSON observation
- show: print config, registry, aggregates, or active observations
- aggregate: deterministically rebuild aggregate statistics from active + archived observations
- compact: archive older active observations once configured thresholds are exceeded

Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
APP_NAME = "orca-orchestrator"

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "exploration": {"enabled": True},
    "limits": {
        "max_rework_rounds": 2,
        "max_spec_revisions": 1,
        "max_dispatches": 8,
        "max_elapsed_minutes": None,
        "blocking_wait_minutes": 15,
    },
    "compaction": {
        "enabled": True,
        "max_active_observations_per_combination": 50,
        "archive_batch_size_per_combination": 25,
        "stale_after_days": 90,
    },
}


def config_root() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def state_root() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / APP_NAME


def config_path() -> Path:
    return config_root() / "config.json"


def registry_path() -> Path:
    return state_root() / "registry.json"


def capabilities_path() -> Path:
    return state_root() / "capabilities.json"


def aggregates_path() -> Path:
    return state_root() / "aggregates.json"


def observations_path() -> Path:
    return state_root() / "observations.jsonl"


def archive_root() -> Path:
    return state_root() / "archive"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_jsonl_atomic(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for value in values:
            fh.write(json.dumps(value, sort_keys=True) + "\n")
    tmp.replace(path)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def ensure_supported_schema(value: dict[str, Any], source: str) -> None:
    version = value.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"{source}: unsupported schema_version {version!r}; expected {SCHEMA_VERSION}"
        )


def merge_defaults(value: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = dict(value)
    for key, default in defaults.items():
        if key not in merged:
            merged[key] = default
        elif isinstance(default, dict) and isinstance(merged[key], dict):
            merged[key] = merge_defaults(merged[key], default)
    return merged


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: config must be a JSON object")
    ensure_supported_schema(value, "config")
    return merge_defaults(value, DEFAULT_CONFIG)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    values: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            ensure_supported_schema(value, f"{path}:{line_number}")
            values.append(value)
    return values


def all_observations() -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for path in sorted(archive_root().glob("observations-*.jsonl")):
        values.extend(read_jsonl(path))
    values.extend(read_jsonl(observations_path()))
    return values


def init_state() -> None:
    cfg = config_path()
    reg = registry_path()
    caps = capabilities_path()
    agg = aggregates_path()
    obs = observations_path()
    archive = archive_root()

    if cfg.exists():
        value = load_json(cfg)
        if not isinstance(value, dict):
            raise ValueError(f"{cfg}: config must be a JSON object")
        ensure_supported_schema(value, "config")
        merged = merge_defaults(value, DEFAULT_CONFIG)
        if merged != value:
            write_json_atomic(cfg, merged)
    else:
        write_json_atomic(cfg, DEFAULT_CONFIG)

    if not reg.exists():
        write_json_atomic(
            reg,
            {
                "schema_version": SCHEMA_VERSION,
                "updated_at": utc_now(),
                "harnesses": {},
                "models": {},
                "combinations": {},
                "role_combinations": {},
            },
        )
    else:
        value = load_json(reg)
        if not isinstance(value, dict):
            raise ValueError(f"{reg}: registry must be a JSON object")
        ensure_supported_schema(value, "registry")

    if not caps.exists():
        write_json_atomic(
            caps,
            {
                "schema_version": SCHEMA_VERSION,
                "updated_at": utc_now(),
                "tools": {},
                "backends": {},
                "cloud": {},
            },
        )
    else:
        value = load_json(caps)
        if not isinstance(value, dict):
            raise ValueError(f"{caps}: capabilities must be a JSON object")
        ensure_supported_schema(value, "capabilities")

    archive.mkdir(parents=True, exist_ok=True)
    obs.parent.mkdir(parents=True, exist_ok=True)
    obs.touch(exist_ok=True)

    if not agg.exists():
        write_aggregates()

    print(f"config:       {cfg}")
    print(f"registry:     {reg}")
    print(f"capabilities: {caps}")
    print(f"aggregates:   {agg}")
    print(f"observations: {obs}")
    print(f"archive:      {archive}")


def write_capabilities(discovered: dict[str, Any]) -> None:
    """Persist discover.py output as the mechanical capability snapshot.

    Unlike registry.json (revisable beliefs derived from observations),
    capabilities.json is fully overwritten on each write: it reflects what
    was observed to be locally available just now, not accumulated history.
    """
    value = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": utc_now(),
        "tools": discovered.get("tools", {}),
        "backends": discovered.get("backends", {}),
        "cloud": discovered.get("cloud", {}),
    }
    write_json_atomic(capabilities_path(), value)


def combination_key(value: dict[str, Any]) -> str:
    harness = str(value.get("harness") or "unknown")
    model = str(value.get("model") or "unknown")
    backend = str(value.get("backend") or "unknown")
    effort = str(value.get("effort") or "none")
    variant = str(value.get("model_variant") or "none")
    return f"{harness}|{model}|{backend}|{effort}|{variant}"


def role_combination_key(value: dict[str, Any]) -> str:
    role = str(value.get("role") or "unknown")
    return f"{role}|{combination_key(value)}"


def observation_kind(value: dict[str, Any]) -> str:
    return str(value.get("kind") or "execution")


def observation_group_key(value: dict[str, Any]) -> str:
    """Group key used for compaction thresholds; mirrors the aggregation split
    between execution observations (grouped by combination) and task
    observations (grouped by task type), so unrelated kinds are never merged
    into the same active/archive bucket."""
    if observation_kind(value) == "task":
        return f"task|{value.get('task_type') or 'unknown'}"
    return combination_key(value)


def new_bucket() -> dict[str, Any]:
    return {
        "observations": 0,
        "completed": 0,
        "owner_interventions_total": 0,
        "owner_interventions_observed": 0,
        "review_verdicts": {},
        "rework_rounds_total": 0,
        "rework_rounds_observed": 0,
        "takeovers": 0,
        "termination_reasons": {},
        "recent_observations": 0,
        "last_observed_at": None,
    }


def update_bucket(
    bucket: dict[str, Any],
    observation: dict[str, Any],
    cutoff: datetime,
) -> None:
    bucket["observations"] += 1
    if observation.get("completed") is True:
        bucket["completed"] += 1

    owner_interventions = observation.get("owner_interventions")
    if isinstance(owner_interventions, int) and not isinstance(owner_interventions, bool):
        bucket["owner_interventions_total"] += owner_interventions
        bucket["owner_interventions_observed"] += 1

    verdict = observation.get("review_verdict")
    if isinstance(verdict, str) and verdict:
        bucket["review_verdicts"][verdict] = bucket["review_verdicts"].get(verdict, 0) + 1

    rework_rounds = observation.get("rework_rounds")
    if isinstance(rework_rounds, int) and not isinstance(rework_rounds, bool):
        bucket["rework_rounds_total"] += rework_rounds
        bucket["rework_rounds_observed"] += 1

    if observation.get("takeover") is True:
        bucket["takeovers"] += 1

    reason = observation.get("termination_reason")
    if isinstance(reason, str) and reason:
        bucket["termination_reasons"][reason] = (
            bucket["termination_reasons"].get(reason, 0) + 1
        )

    timestamp = observation.get("timestamp")
    if isinstance(timestamp, str):
        current = bucket["last_observed_at"]
        if current is None or timestamp > current:
            bucket["last_observed_at"] = timestamp

    parsed = parse_timestamp(timestamp)
    if parsed is not None and parsed >= cutoff:
        bucket["recent_observations"] += 1


def finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    result = dict(bucket)
    observations = result["observations"]
    result["completion_rate"] = result["completed"] / observations if observations else None

    observed_owner = result["owner_interventions_observed"]
    result["mean_owner_interventions"] = (
        result["owner_interventions_total"] / observed_owner if observed_owner else None
    )

    observed_rework = result["rework_rounds_observed"]
    result["mean_rework_rounds"] = (
        result["rework_rounds_total"] / observed_rework if observed_rework else None
    )
    return result


def build_aggregates(
    observations: list[dict[str, Any]],
    *,
    stale_after_days: int,
) -> dict[str, Any]:
    """Build deterministic aggregates from raw observations.

    `harnesses`/`models`/`combinations`/`role_combinations` are derived only
    from `kind: "execution"` observations, since only those carry a
    well-defined harness/model/backend. `tasks` is derived only from
    `kind: "task"` observations (one per task, holding task-level outcome
    fields such as owner_interventions/review_verdict/rework_rounds), so a
    task's final outcome is never double-counted across its per-role
    execution observations. See references/state.md#observation-schema.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_after_days)

    harnesses: dict[str, dict[str, Any]] = defaultdict(new_bucket)
    models: dict[str, dict[str, Any]] = defaultdict(new_bucket)
    combinations: dict[str, dict[str, Any]] = defaultdict(new_bucket)
    role_combinations: dict[str, dict[str, Any]] = defaultdict(new_bucket)
    tasks: dict[str, dict[str, Any]] = defaultdict(new_bucket)

    for observation in observations:
        if observation_kind(observation) == "task":
            task_type = str(observation.get("task_type") or "unknown")
            update_bucket(tasks[task_type], observation, cutoff)
            continue

        harness = str(observation.get("harness") or "unknown")
        model = str(observation.get("model") or "unknown")
        update_bucket(harnesses[harness], observation, cutoff)
        update_bucket(models[model], observation, cutoff)
        update_bucket(combinations[combination_key(observation)], observation, cutoff)
        update_bucket(role_combinations[role_combination_key(observation)], observation, cutoff)

    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": utc_now(),
        "stale_after_days": stale_after_days,
        "harnesses": {key: finalize_bucket(value) for key, value in sorted(harnesses.items())},
        "models": {key: finalize_bucket(value) for key, value in sorted(models.items())},
        "combinations": {
            key: finalize_bucket(value) for key, value in sorted(combinations.items())
        },
        "role_combinations": {
            key: finalize_bucket(value) for key, value in sorted(role_combinations.items())
        },
        "tasks": {key: finalize_bucket(value) for key, value in sorted(tasks.items())},
    }


def write_aggregates() -> None:
    cfg = load_config()
    settings = cfg["compaction"]
    stale_after_days = int(settings["stale_after_days"])
    if stale_after_days < 0:
        raise ValueError("compaction.stale_after_days must be >= 0")
    value = build_aggregates(all_observations(), stale_after_days=stale_after_days)
    write_json_atomic(aggregates_path(), value)


# Required fields differ by kind: an "execution" observation describes one
# role's dispatch (needs a harness/model to be a meaningful combination
# data point) and a "task" observation describes the whole task's outcome
# (no single harness/model applies). See references/state.md#observation-schema.
REQUIRED_FIELDS_BY_KIND = {
    "execution": ("task_id", "role", "harness", "model"),
    "task": ("task_id", "task_type"),
}

# task.py counters that a "task"-kind observation should inherit from the
# task's own deterministic guardrail state rather than have the LLM retype,
# so the two never drift apart.
TASK_COUNTER_FIELDS = (
    "dispatches",
    "rework_rounds",
    "spec_revisions",
    "technical_retries",
    "blocking_timeouts",
)


def task_state_path(task_id: str) -> Path:
    if not task_id or "/" in task_id or "\\" in task_id or ".." in task_id:
        raise ValueError("task_id must not be empty or contain '/', '\\', or '..'")
    return state_root() / "tasks" / f"{task_id}.json"


def load_task_state(task_id: str) -> dict[str, Any] | None:
    path = task_state_path(task_id)
    if not path.exists():
        return None
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: task state must be a JSON object")
    ensure_supported_schema(value, f"task {task_id!r}")
    return value


def append_observation(raw: str, *, task_id: str | None = None) -> None:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("observation must be a JSON object")

    value.setdefault("schema_version", SCHEMA_VERSION)
    value.setdefault("timestamp", utc_now())
    ensure_supported_schema(value, "observation")

    kind = value.get("kind")
    if kind not in REQUIRED_FIELDS_BY_KIND:
        raise ValueError(
            "observation must set 'kind' to one of: "
            + ", ".join(sorted(REQUIRED_FIELDS_BY_KIND))
        )

    if task_id is not None:
        value.setdefault("task_id", task_id)
        task_state = load_task_state(task_id)
        if task_state is None:
            raise ValueError(f"task {task_id!r} not started; run 'task.py start' first")
        if kind == "task":
            counters = task_state["counters"]
            for field in TASK_COUNTER_FIELDS:
                value.setdefault(field, counters[field])
            if task_state.get("termination_reason") is not None:
                value.setdefault("termination_reason", task_state["termination_reason"])

    required = REQUIRED_FIELDS_BY_KIND[kind]
    missing = [field for field in required if not value.get(field)]
    if missing:
        raise ValueError(f"observation missing required field(s): {', '.join(missing)}")

    path = observations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(value, sort_keys=True) + "\n")

    write_aggregates()
    maybe_compact()
    print(f"appended observation to {path}")


def maybe_compact() -> None:
    cfg = load_config()
    settings = cfg["compaction"]
    if not settings.get("enabled", True):
        return

    max_active = int(settings["max_active_observations_per_combination"])
    if max_active < 1:
        raise ValueError("compaction.max_active_observations_per_combination must be >= 1")

    active = read_jsonl(observations_path())
    counts: dict[str, int] = defaultdict(int)
    for observation in active:
        counts[observation_group_key(observation)] += 1
    if any(count > max_active for count in counts.values()):
        compact_state(quiet=True)


def next_archive_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = archive_root() / f"observations-{stamp}.jsonl"
    if not base.exists():
        return base
    index = 1
    while True:
        candidate = archive_root() / f"observations-{stamp}-{index}.jsonl"
        if not candidate.exists():
            return candidate
        index += 1


def compact_state(*, quiet: bool = False) -> None:
    cfg = load_config()
    settings = cfg["compaction"]

    if not settings.get("enabled", True):
        write_aggregates()
        if not quiet:
            print("compaction disabled; aggregates refreshed")
        return

    max_active = int(settings["max_active_observations_per_combination"])
    archive_batch = int(settings["archive_batch_size_per_combination"])
    if max_active < 1:
        raise ValueError("compaction.max_active_observations_per_combination must be >= 1")
    if archive_batch < 1:
        raise ValueError("compaction.archive_batch_size_per_combination must be >= 1")

    active = read_jsonl(observations_path())
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, observation in enumerate(active):
        grouped[observation_group_key(observation)].append(index)

    selected: set[int] = set()
    for indices in grouped.values():
        if len(indices) <= max_active:
            continue

        ordered = sorted(
            indices,
            key=lambda index: (str(active[index].get("timestamp") or ""), index),
        )
        archive_count = max(archive_batch, len(indices) - max_active)
        archive_count = min(archive_count, len(indices))
        selected.update(ordered[:archive_count])

    if selected:
        archived = [value for index, value in enumerate(active) if index in selected]
        remaining = [value for index, value in enumerate(active) if index not in selected]

        archive_root().mkdir(parents=True, exist_ok=True)
        archive_path = next_archive_path()
        write_jsonl_atomic(archive_path, archived)
        write_jsonl_atomic(observations_path(), remaining)

        if not quiet:
            print(f"archived {len(archived)} observations to {archive_path}")
            print(f"active observations remaining: {len(remaining)}")
    elif not quiet:
        print("no compaction required")

    write_aggregates()


def show(kind: str) -> None:
    if kind == "config":
        print(json.dumps(load_config(), indent=2, sort_keys=True))
        return

    if kind == "registry":
        path = registry_path()
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run init first")
        value = load_json(path)
        if not isinstance(value, dict):
            raise ValueError(f"{path}: registry must be a JSON object")
        ensure_supported_schema(value, "registry")
        print(json.dumps(value, indent=2, sort_keys=True))
        return

    if kind == "aggregates":
        path = aggregates_path()
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run init first")
        value = load_json(path)
        if not isinstance(value, dict):
            raise ValueError(f"{path}: aggregates must be a JSON object")
        ensure_supported_schema(value, "aggregates")
        print(json.dumps(value, indent=2, sort_keys=True))
        return

    if kind == "capabilities":
        path = capabilities_path()
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run init first")
        value = load_json(path)
        if not isinstance(value, dict):
            raise ValueError(f"{path}: capabilities must be a JSON object")
        ensure_supported_schema(value, "capabilities")
        print(json.dumps(value, indent=2, sort_keys=True))
        return

    path = observations_path()
    if not path.exists():
        raise FileNotFoundError(f"missing {path}; run init first")
    sys.stdout.write(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="initialize config and state files")

    observe = sub.add_parser("observe", help="append a JSON observation")
    observe.add_argument(
        "json",
        help="observation as a JSON object; schema_version/timestamp are added if omitted",
    )
    observe.add_argument(
        "--task-id",
        help=(
            "stamp task_id onto the observation and, for kind:task, fill "
            "dispatch/rework/spec-revision/retry/blocking counters and "
            "termination_reason from tasks/<task_id>.json instead of "
            "retyping them (explicit values in the JSON body still win)"
        ),
    )

    show_parser = sub.add_parser("show", help="show current state")
    show_parser.add_argument(
        "kind", choices=("config", "registry", "capabilities", "aggregates", "observations")
    )

    sub.add_parser(
        "aggregate",
        help="rebuild deterministic aggregate statistics from active and archived observations",
    )
    sub.add_parser(
        "compact",
        help="archive older active observations according to configured thresholds",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            init_state()
        elif args.command == "observe":
            append_observation(args.json, task_id=args.task_id)
        elif args.command == "show":
            show(args.kind)
        elif args.command == "aggregate":
            write_aggregates()
            print(f"updated aggregates at {aggregates_path()}")
        elif args.command == "compact":
            compact_state()
        else:
            raise AssertionError(args.command)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
