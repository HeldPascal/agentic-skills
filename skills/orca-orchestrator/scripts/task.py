#!/usr/bin/env python3
"""Deterministically track per-task orchestration guardrail counters.

Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state as state_helper  # noqa: E402


SCHEMA_VERSION = 1
LIMIT_KEYS = (
    "max_rework_rounds",
    "max_spec_revisions",
    "max_dispatches",
    "max_elapsed_minutes",
)
EVENT_COUNTERS = {
    "dispatch": "dispatches",
    "rework": "rework_rounds",
    "spec_revision": "spec_revisions",
    "technical_retry": "technical_retries",
    "blocking_timeout": "blocking_timeouts",
}


def validate_task_id(task_id: str) -> None:
    if not task_id:
        raise ValueError("task_id must not be empty")
    if "/" in task_id or "\\" in task_id or ".." in task_id:
        raise ValueError("task_id must not contain '/', '\\', or '..'")


def task_path(task_id: str) -> Path:
    validate_task_id(task_id)
    return state_helper.state_root() / "tasks" / f"{task_id}.json"


def load_task(task_id: str) -> dict[str, Any]:
    path = task_path(task_id)
    if not path.exists():
        raise ValueError(f"task {task_id!r} not started; run 'task.py start' first")
    value = state_helper.load_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: task state must be a JSON object")
    state_helper.ensure_supported_schema(value, f"task {task_id!r}")
    return value


def parse_limits(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("--limits-json must be a JSON object")
    unknown = sorted(set(value) - set(LIMIT_KEYS))
    if unknown:
        raise ValueError(f"unknown limit key(s): {', '.join(unknown)}")
    return value


def start_task(task_id: str, limits_json: str | None) -> dict[str, Any]:
    path = task_path(task_id)
    overrides = parse_limits(limits_json)
    if path.exists():
        return load_task(task_id)

    configured = state_helper.load_config()["limits"]
    limits = {key: configured[key] for key in LIMIT_KEYS}
    limits.update(overrides)
    value = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "started_at": state_helper.utc_now(),
        "finished_at": None,
        "status": "active",
        "termination_reason": None,
        "limits": limits,
        "counters": {
            "dispatches": 0,
            "rework_rounds": 0,
            "spec_revisions": 0,
            "technical_retries": 0,
            "blocking_timeouts": 0,
        },
    }
    state_helper.write_json_atomic(path, value)
    return value


def elapsed_minutes(value: dict[str, Any]) -> float:
    started = state_helper.parse_timestamp(value.get("started_at"))
    if started is None:
        raise ValueError("task started_at must be a valid timestamp")
    if value.get("finished_at") is None:
        ended = datetime.now(timezone.utc)
    else:
        ended = state_helper.parse_timestamp(value.get("finished_at"))
        if ended is None:
            raise ValueError("task finished_at must be a valid timestamp")
    return (ended - started).total_seconds() / 60.0


def status_value(value: dict[str, Any]) -> dict[str, Any]:
    elapsed = elapsed_minutes(value)
    limits = value["limits"]
    counters = value["counters"]

    def reached(counter: str, limit: str) -> bool:
        ceiling = limits[limit]
        return ceiling is not None and counters[counter] >= ceiling

    return {
        **value,
        "elapsed_minutes": elapsed,
        "limit_reached": {
            "dispatches": reached("dispatches", "max_dispatches"),
            "rework_rounds": reached("rework_rounds", "max_rework_rounds"),
            "spec_revisions": reached("spec_revisions", "max_spec_revisions"),
            "elapsed_minutes": limits["max_elapsed_minutes"] is not None
            and elapsed >= limits["max_elapsed_minutes"],
        },
    }


def print_status(value: dict[str, Any]) -> None:
    print(json.dumps(status_value(value), indent=2, sort_keys=True))


def record_event(task_id: str, event: str) -> dict[str, Any]:
    value = load_task(task_id)
    if value.get("status") == "finished":
        raise ValueError(f"task {task_id!r} is already finished")
    value["counters"][EVENT_COUNTERS[event]] += 1
    state_helper.write_json_atomic(task_path(task_id), value)
    return value


def finish_task(task_id: str, termination_reason: str | None) -> dict[str, Any]:
    value = load_task(task_id)
    value["status"] = "finished"
    value["finished_at"] = state_helper.utc_now()
    value["termination_reason"] = termination_reason
    state_helper.write_json_atomic(task_path(task_id), value)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="start per-task guardrail tracking")
    start.add_argument("task_id")
    start.add_argument("--limits-json", help="JSON object overriding task limits")

    record = sub.add_parser("record", help="increment a task guardrail counter")
    record.add_argument("task_id")
    record.add_argument("--event", choices=tuple(EVENT_COUNTERS), required=True)

    status = sub.add_parser("status", help="show task counters and limit status")
    status.add_argument("task_id")

    finish = sub.add_parser("finish", help="finish task guardrail tracking")
    finish.add_argument("task_id")
    finish.add_argument("--termination-reason")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "start":
            print_status(start_task(args.task_id, args.limits_json))
        elif args.command == "record":
            print_status(record_event(args.task_id, args.event))
        elif args.command == "status":
            print_status(load_task(args.task_id))
        elif args.command == "finish":
            print_status(finish_task(args.task_id, args.termination_reason))
        else:
            raise AssertionError(args.command)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
