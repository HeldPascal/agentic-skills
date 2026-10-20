#!/usr/bin/env python3
"""Run targeted, process-local mutation probes against a pytest suite.

Each mutant replaces one exact source fragment of one importable Python module.
The replacement happens only inside a fresh child interpreter: an import hook
compiles the mutated source the first time the target module is imported
(normally while pytest collects the tests), so the module runs exactly once,
with the project's normal import configuration. No file is modified.

Usage (run inside the project's environment so the code and pytest import):

    uv run python probe_pytest.py --mutants mutants.json [--json result.json] \
        [--timeout 600] -- tests/area -q

mutants.json is a list of objects with keys ``id``, ``module``, ``old``,
``new`` and an optional ``description``. ``old`` must occur exactly once in
the module source.

Statuses: KILLED (tests failed), FAILED (tests could not be collected because
of the mutation - read the output to judge it), SURVIVED, NOT_EXERCISED (the
selected tests never imported the target module in-process), INVALID (``old``
not unique), ERROR, TIMEOUT. Exit status: 0 when every mutant was killed, 1
when at least one survived and none needs attention, 2 for invalid input, a
failing baseline, or any INVALID, ERROR, NOT_EXERCISED or TIMEOUT result, 3
when nothing survived but FAILED results need judgment.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_STATE_PREFIX = "PROBE-STATE "
_TAIL_LINES = 30

# Runs in the child interpreter. The finder hands the target module a loader
# that compiles mutated source instead of reading the file or bytecode cache.
# A pytest plugin keeps the finder ahead of pytest's assertion-rewriting hook.
_CHILD = r"""
import importlib.abc, importlib.machinery, importlib.util, json, sys
spec = json.loads(sys.stdin.read())
mutant = spec["mutant"]
state = {"status": "not_imported"}
plugins = []
if mutant is not None:
    sys.dont_write_bytecode = True

    class MutatingLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            try:
                source = importlib.util.decode_source(self.get_data(self.path))
            except Exception as exc:
                state["status"] = f"error: cannot read source: {exc!r}"
                raise
            count = source.count(mutant["old"])
            if count != 1:
                state["status"] = f"invalid: 'old' occurs {count} times"
                raise ImportError(f"probe: 'old' occurs {count} times in {self.path}")
            try:
                code = compile(
                    source.replace(mutant["old"], mutant["new"]),
                    self.path, "exec", dont_inherit=True,
                )
            except SyntaxError as exc:
                state["status"] = f"error: mutated source does not compile: {exc}"
                raise
            state["status"] = "applied"
            return code

    class MutatingFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != mutant["module"]:
                return None
            for finder in sys.meta_path:
                if (
                    finder is self
                    or type(finder).__name__ == "AssertionRewritingHook"
                    or not hasattr(finder, "find_spec")
                ):
                    continue
                found = finder.find_spec(name, path, target)
                if found is not None:
                    break
            else:
                return None
            loader = found.loader
            # Only the plain loader is safe to replace; subclasses may add behavior.
            if type(loader) is not importlib.machinery.SourceFileLoader:
                state["status"] = f"error: unsupported loader {type(loader).__name__}"
                return found
            found.loader = MutatingLoader(loader.name, loader.path)
            return found

    finder = MutatingFinder()
    sys.meta_path.insert(0, finder)
    import pytest

    class KeepFinderFirst:
        @pytest.hookimpl(tryfirst=True)
        def pytest_load_initial_conftests(self):
            sys.meta_path.remove(finder)
            sys.meta_path.insert(0, finder)

    plugins.append(KeepFinderFirst())
import pytest
code = pytest.main(spec["pytest_args"], plugins=plugins)
if (
    mutant is not None
    and state["status"] == "not_imported"
    and mutant["module"] in sys.modules
):
    state["status"] = "error: target was imported without the probe hook"
sys.stdout.flush()
print("PROBE-STATE " + json.dumps(state["status"]))
sys.exit(code)
"""


@dataclass(frozen=True)
class Mutant:
    id: str
    module: str
    old: str
    new: str
    description: str = ""


@dataclass(frozen=True)
class Outcome:
    id: str
    status: str
    detail: str
    description: str
    output_tail: list[str] = field(default_factory=list)


def load_mutants(path: Path) -> list[Mutant]:
    """Load and validate the mutant list from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("mutants file must contain a nonempty JSON list")
    mutants: list[Mutant] = []
    seen: set[str] = set()
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"mutant {index} must be an object")  # noqa: TRY004
        missing = {"id", "module", "old", "new"} - entry.keys()
        if missing:
            raise ValueError(f"mutant {index} lacks {sorted(missing)}")
        unknown = entry.keys() - {"id", "module", "old", "new", "description"}
        if unknown:
            raise ValueError(f"mutant {index} has unknown keys {sorted(unknown)}")
        if not all(isinstance(value, str) for value in entry.values()):
            raise ValueError(f"mutant {index} values must be strings")
        if entry["id"] in seen:
            raise ValueError(f"duplicate mutant id {entry['id']!r}")
        if entry["old"] == entry["new"]:
            raise ValueError(f"mutant {entry['id']!r} does not change anything")
        seen.add(entry["id"])
        mutants.append(Mutant(**entry))
    return mutants


@dataclass(frozen=True)
class _ChildResult:
    returncode: int | None
    state: str | None
    lines: list[str]


def _run_child(
    mutant: Mutant | None,
    pytest_args: list[str],
    python: str,
    timeout: float,
) -> _ChildResult:
    payload = json.dumps(
        {
            "mutant": None if mutant is None else asdict(mutant),
            "pytest_args": pytest_args,
        }
    )
    # Own process group, so a timeout also stops processes the tests started.
    process = subprocess.Popen(
        [python, "-c", _CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return _ChildResult(None, None, [f"timed out after {timeout:g}s"])
    state = None
    lines = []
    for line in output.splitlines():
        if line.startswith(_STATE_PREFIX):
            state = json.loads(line[len(_STATE_PREFIX) :])
        elif line.strip():
            lines.append(line)
    return _ChildResult(process.returncode, state, lines)


def classify(result: _ChildResult) -> str:
    """Map a mutant run to a probe status."""
    if result.returncode is None:
        return "TIMEOUT"
    if result.state is None or result.state.startswith("error"):
        return "ERROR"
    if result.state.startswith("invalid"):
        return "INVALID"
    if result.state == "not_imported":
        return "NOT_EXERCISED"
    if result.returncode == 0:
        return "SURVIVED"
    if result.returncode == 1:
        return "KILLED"
    # 2: collection errors - the mutation broke loading, not necessarily a test.
    if result.returncode == 2:
        return "FAILED"
    return "ERROR"


def run_probes(
    mutants: list[Mutant],
    pytest_args: list[str],
    *,
    python: str = sys.executable,
    timeout: float = 600.0,
) -> tuple[Outcome, list[Outcome]]:
    """Run the unmutated baseline, then every mutant in its own process."""
    base = _run_child(None, pytest_args, python, timeout)
    baseline = Outcome(
        "baseline",
        "PASSED" if base.returncode == 0 else "FAILED",
        base.lines[-1] if base.lines else "",
        "",
        base.lines[-_TAIL_LINES:],
    )
    if base.returncode != 0:
        return baseline, []
    outcomes = []
    for mutant in mutants:
        result = _run_child(mutant, pytest_args, python, timeout)
        status = classify(result)
        detail = result.lines[-1] if result.lines else ""
        if status in {"ERROR", "INVALID"} and result.state:
            detail = result.state
        outcomes.append(
            Outcome(
                mutant.id,
                status,
                detail,
                mutant.description,
                result.lines[-_TAIL_LINES:],
            )
        )
    return baseline, outcomes


def _format(baseline: Outcome, outcomes: list[Outcome]) -> str:
    lines = [f"baseline: {baseline.status} ({baseline.detail})"]
    for outcome in outcomes:
        lines.append(f"{outcome.status:13} {outcome.id}: {outcome.description}")
        lines.append(f"              {outcome.detail}")
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    lines.append("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutants", type=Path, required=True)
    parser.add_argument("--json", type=Path, help="write results as JSON")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--python", default=sys.executable, help="interpreter for test runs"
    )
    parser.add_argument("pytest_args", nargs="*", help="arguments after --")
    args = parser.parse_args(argv)
    try:
        mutants = load_mutants(args.mutants)
    except (OSError, ValueError) as exc:
        print(f"probe: {exc}", file=sys.stderr)
        return 2
    baseline, outcomes = run_probes(
        mutants, args.pytest_args, python=args.python, timeout=args.timeout
    )
    print(_format(baseline, outcomes))
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "baseline": asdict(baseline),
                    "mutants": [asdict(outcome) for outcome in outcomes],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    if baseline.status != "PASSED":
        return 2
    statuses = {outcome.status for outcome in outcomes}
    if statuses & {"INVALID", "ERROR", "TIMEOUT", "NOT_EXERCISED"}:
        return 2
    if "SURVIVED" in statuses:
        return 1
    return 3 if "FAILED" in statuses else 0


if __name__ == "__main__":
    sys.exit(main())
