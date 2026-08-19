#!/usr/bin/env python3
"""Minimal state helper for the orca-orchestrator skill.

v0.1 supports:
- init: create config/state files if missing
- observe: append one JSON observation
- show: print config, registry, or observations

Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
APP_NAME = "orca-orchestrator"


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


def observations_path() -> Path:
    return state_root() / "observations.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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


def init_state() -> None:
    cfg = config_path()
    reg = registry_path()
    obs = observations_path()

    if not cfg.exists():
        write_json_atomic(
            cfg,
            {
                "schema_version": SCHEMA_VERSION,
                "exploration": {"enabled": True},
            },
        )

    if not reg.exists():
        write_json_atomic(
            reg,
            {
                "schema_version": SCHEMA_VERSION,
                "updated_at": utc_now(),
                "harnesses": {},
                "models": {},
                "combinations": {},
            },
        )

    obs.parent.mkdir(parents=True, exist_ok=True)
    obs.touch(exist_ok=True)

    print(f"config:       {cfg}")
    print(f"registry:     {reg}")
    print(f"observations: {obs}")


def append_observation(raw: str) -> None:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("observation must be a JSON object")

    value.setdefault("schema_version", SCHEMA_VERSION)
    value.setdefault("timestamp", utc_now())
    ensure_supported_schema(value, "observation")

    required = ("task_type", "harness", "model")
    missing = [field for field in required if not value.get(field)]
    if missing:
        raise ValueError(f"observation missing required field(s): {', '.join(missing)}")

    path = observations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(value, sort_keys=True) + "\n")

    print(f"appended observation to {path}")


def show(kind: str) -> None:
    if kind == "config":
        path = config_path()
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run init first")
        value = load_json(path)
        ensure_supported_schema(value, "config")
        print(json.dumps(value, indent=2, sort_keys=True))
        return

    if kind == "registry":
        path = registry_path()
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run init first")
        value = load_json(path)
        ensure_supported_schema(value, "registry")
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

    show_parser = sub.add_parser("show", help="show current state")
    show_parser.add_argument("kind", choices=("config", "registry", "observations"))

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            init_state()
        elif args.command == "observe":
            append_observation(args.json)
        elif args.command == "show":
            show(args.kind)
        else:
            raise AssertionError(args.command)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
