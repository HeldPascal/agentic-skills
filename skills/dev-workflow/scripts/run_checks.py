#!/usr/bin/env python3
"""Run a project's established verification commands in named stages.

Stages and commands come from a small JSON file the coordinator writes once per
project from the repository's documented commands, for example:

    {"fast": [{"name": "lint", "cmd": "uv run ruff check ."}],
     "full": [{"name": "tests", "cmd": "uv run pytest -q"}]}

Usage:
    run_checks.py --config checks.json --stage fast [--stage full]
                  [--cwd DIR] [--log-dir DIR]

Every command of the selected stages runs (a failure does not stop later
commands), its full output goes to a fresh timestamped subdirectory of the
log directory (earlier evidence is never overwritten), and a summary with the
last output line of each command is printed. Exit status 0 if all passed,
1 if any failed, 2 for invalid configuration.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Check:
    stage: str
    name: str
    cmd: str


@dataclass(frozen=True)
class Result:
    check: Check
    returncode: int
    seconds: float
    last_line: str
    log: Path | None


def load_checks(path: Path, stages: list[str]) -> list[Check]:
    """Load the commands of the requested stages, in stage order."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("checks file must contain a JSON object of stages")  # noqa: TRY004
    checks: list[Check] = []
    seen: set[tuple[str, str]] = set()
    for stage in stages:
        if stage not in data:
            raise ValueError(f"unknown stage {stage!r}; have {sorted(data)}")
        entries = data[stage]
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"stage {stage!r} must be a nonempty list")
        for index, entry in enumerate(entries):
            if (
                not isinstance(entry, dict)
                or set(entry) != {"name", "cmd"}
                or not all(isinstance(v, str) and v.strip() for v in entry.values())
            ):
                raise ValueError(
                    f"{stage}[{index}] needs exactly a nonempty 'name' and 'cmd'"
                )
            if (stage, entry["name"]) in seen:
                raise ValueError(f"duplicate check name {entry['name']!r} in {stage!r}")
            seen.add((stage, entry["name"]))
            checks.append(Check(stage, entry["name"], entry["cmd"]))
    return checks


def run(check: Check, cwd: Path, log_dir: Path | None, ordinal: int = 1) -> Result:
    started = time.monotonic()
    completed = subprocess.run(
        check.cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    seconds = time.monotonic() - started
    output = completed.stdout + completed.stderr
    log = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{check.stage}-{check.name}")
        log = log_dir / f"{ordinal:02d}-{slug}.log"
        log.write_text(f"$ {check.cmd}\n{output}", encoding="utf-8")
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return Result(check, completed.returncode, seconds, lines[-1] if lines else "", log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", action="append", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--log-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        checks = load_checks(args.config, args.stage)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"run_checks: {exc}", file=sys.stderr)
        return 2
    log_dir = None
    if args.log_dir is not None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        log_dir = args.log_dir / stamp
    results = [
        run(check, args.cwd, log_dir, ordinal)
        for ordinal, check in enumerate(checks, start=1)
    ]
    for result in results:
        verdict = "PASS" if result.returncode == 0 else f"FAIL({result.returncode})"
        print(
            f"{verdict:9} {result.check.stage}/{result.check.name} "
            f"[{result.seconds:.1f}s] {result.last_line}"
        )
        if result.log is not None and result.returncode != 0:
            print(f"          log: {result.log}")
    return 1 if any(result.returncode != 0 for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
