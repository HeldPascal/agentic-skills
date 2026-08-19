#!/usr/bin/env python3
"""Basic health checks for the orca-orchestrator skill runtime."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

APP_NAME = "orca-orchestrator"


def config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def state_root() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / APP_NAME


def check_writable(path: Path) -> tuple[bool, str]:
    target = path if path.exists() else path.parent
    while not target.exists() and target != target.parent:
        target = target.parent
    ok = os.access(target, os.W_OK)
    return ok, f"writable via {target}" if ok else f"not writable via {target}"


def main() -> int:
    checks: list[dict[str, object]] = []

    for tool in ("orca", "codex", "claude", "pi", "opencode", "qwen"):
        path = shutil.which(tool)
        checks.append({"name": f"tool:{tool}", "ok": path is not None, "detail": path})

    for name, path in (("config", config_root()), ("state", state_root())):
        ok, detail = check_writable(path)
        checks.append({"name": f"path:{name}", "ok": ok, "detail": f"{path} ({detail})"})

    orca_available = any(c["name"] == "tool:orca" and c["ok"] for c in checks)
    worker_available = any(
        c["name"] in {"tool:codex", "tool:claude", "tool:pi", "tool:opencode", "tool:qwen"} and c["ok"]
        for c in checks
    )
    paths_ok = all(c["ok"] for c in checks if str(c["name"]).startswith("path:"))

    result = {
        "ok": bool(orca_available and worker_available and paths_ok),
        "checks": checks,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
