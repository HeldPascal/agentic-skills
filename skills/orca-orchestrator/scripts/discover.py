#!/usr/bin/env python3
"""Discover locally available orchestration tools and LM Studio models."""

from __future__ import annotations

import json
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


def main() -> int:
    result = {
        "tools": {name: command_version(command) for name, command in TOOLS.items()},
        "backends": {"lmstudio": lmstudio_models()},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
