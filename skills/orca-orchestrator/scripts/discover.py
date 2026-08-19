#!/usr/bin/env python3
"""Discover locally available orchestration tools and LM Studio models.

Scope: this script can only observe what is locally inspectable — installed
CLIs, a local LM Studio backend, and environment variables that commonly
indicate cloud credentials are configured. It cannot enumerate which cloud
models an account can currently reach, nor query available reasoning/effort
levels: cloud providers do not expose a generic "list models and effort
levels for this key" API, and effort is a request-time parameter, not a
queryable model property. Treat `cloud_auth_signal` as a heuristic hint, not
proof of working cloud access, and treat `known_effort_levels` as static
capability metadata to keep in sync with provider docs, not a live probe.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request

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

# Static, human-maintained capability metadata: effort/reasoning-level
# options known to be configurable for cloud-capable harnesses. Update this
# table when provider documentation changes; do not attempt to derive it
# dynamically.
KNOWN_EFFORT_LEVELS = {
    "codex": ["low", "medium", "high"],
    "claude": ["low", "medium", "high"],
    "pi": ["low", "medium", "high"],
}


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


def main() -> int:
    tools = {name: command_version(command) for name, command in TOOLS.items()}
    result = {
        "tools": tools,
        "backends": {"lmstudio": lmstudio_models()},
        "cloud": {
            name: {
                **cloud_auth_signal(name),
                "known_effort_levels": KNOWN_EFFORT_LEVELS.get(name, []),
            }
            for name in CLOUD_AUTH_ENV
            if tools.get(name, {}).get("available")
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
