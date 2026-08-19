#!/usr/bin/env python3
"""Discover locally available orchestration tools and LM Studio models.

Scope: this script can only observe what is locally inspectable — installed
CLIs, a local LM Studio backend, and environment variables that commonly
indicate cloud credentials are configured. It cannot enumerate which cloud
models an account can currently reach, nor query available reasoning/effort
levels: cloud providers do not expose a generic "list models and effort
levels for this key" API, and effort is a request-time parameter of a given
model/provider, not a harness-wide constant — it also changes faster than a
hardcoded list can track (new levels ship with new model versions). Treat
`cloud_auth_signal` as a heuristic hint, not proof of working cloud access.
For effort, this script only reports whether the harness is known to expose
*some* configurable effort dimension (`effort_configurable`); it does not
enumerate specific level names. Look up current level names from the model
you actually selected, not from this script.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state as state_helper  # noqa: E402

TOOLS = {
    "orca": ["orca", "--version"],
    "codex": ["codex", "--version"],
    "claude": ["claude", "--version"],
    "pi": ["pi", "--version"],
    "opencode": ["opencode", "--version"],
    "qwen": ["qwen", "--version"],
}

# Environment variables commonly set when a harness is configured to use a
# cloud backend. Presence is a heuristic signal, not proof of a working key.
CLOUD_AUTH_ENV = {
    "codex": ["OPENAI_API_KEY"],
    "claude": ["ANTHROPIC_API_KEY"],
    "pi": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
    "opencode": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
    "qwen": ["DASHSCOPE_API_KEY", "OPENAI_API_KEY"],
}

# Harnesses known to expose *some* request-time effort/reasoning-budget
# control for at least one supported model. Deliberately not an enumeration
# of level names: those are a model/provider property that changes with
# each model release, not a stable harness-wide constant, and a hardcoded
# name list would go stale faster than this skill gets updated.
EFFORT_CONFIGURABLE_HARNESSES = {"codex", "claude", "pi"}


def command_version(command: list[str]) -> dict[str, object]:
    executable = shutil.which(command[0])
    if executable is None:
        return {"available": False}
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip().splitlines()
        return {
            "available": True,
            "path": executable,
            "version": output[0] if output else None,
            "exit_code": completed.returncode,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "path": executable, "error": str(exc)}


def lmstudio_models() -> dict[str, object]:
    url = "http://127.0.0.1:1234/api/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "error": str(exc)}

    models = []
    for item in payload.get("models", []):
        if item.get("type") != "llm":
            continue
        models.append(
            {
                "key": item.get("key"),
                "display_name": item.get("display_name"),
                "architecture": item.get("architecture"),
                "format": item.get("format"),
                "quantization": item.get("quantization"),
                "max_context_length": item.get("max_context_length"),
                "capabilities": item.get("capabilities"),
                "selected_variant": item.get("selected_variant"),
                "loaded": bool(item.get("loaded_instances")),
            }
        )

    return {"available": True, "url": url, "models": models}


def cloud_auth_signal(name: str) -> dict[str, object]:
    env_vars = CLOUD_AUTH_ENV.get(name, [])
    present = [var for var in env_vars if os.environ.get(var)]
    return {
        "checked_env_vars": env_vars,
        "any_present": bool(present),
        "present_env_vars": present,
    }


def discover() -> dict[str, object]:
    tools = {name: command_version(command) for name, command in TOOLS.items()}
    return {
        "tools": tools,
        "backends": {"lmstudio": lmstudio_models()},
        "cloud": {
            name: {
                **cloud_auth_signal(name),
                "effort_configurable": name in EFFORT_CONFIGURABLE_HARNESSES,
            }
            for name in CLOUD_AUTH_ENV
            if tools.get(name, {}).get("available")
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "also persist the result to capabilities.json (state root); "
            "overwrites the prior snapshot rather than merging it"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = discover()
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.write:
        state_helper.write_capabilities(result)
        print(f"wrote {state_helper.capabilities_path()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
