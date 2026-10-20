#!/usr/bin/env python3
"""Run targeted mutation probes in a scratch git worktree, for any language.

Each mutant replaces one exact text fragment in one file. The probes run
sequentially in a temporary detached worktree of the repository: the unmutated
baseline first, then for every mutant the fragment is replaced, the test
command runs, and the file is restored. Your own working tree is never
touched; the scratch worktree is removed at the end.

Usage:
    probe_files.py --mutants mutants.json [--repo DIR] [--ref REF]
                   [--json result.json] [--timeout 600] -- <test command...>

mutants.json is a list of objects with keys ``id``, ``file`` (path relative to
the repository root), ``old``, ``new`` and an optional ``description``. The
test command runs through the shell in the scratch worktree root; a zero exit
status means the tests passed. Probes run against the committed state at REF
(default HEAD) - commit or stash-apply what you want to probe first.

A nonzero exit status does not by itself show that a test detected the
defect - the mutation may just break the build or test discovery. Where the
runner uses a distinct exit code for failing tests (e.g. pytest: ``1``), pass
it with ``--test-failure-codes``. Runners that share one code for build and
test failures (e.g. cargo, go) cannot be separated by exit code.

Statuses: KILLED (exit code listed in --test-failure-codes), FAILED (any other
nonzero exit - read the output tail to judge whether tests caught the defect
or the run broke), SURVIVED, INVALID (file missing, resolving outside the
repository through a symlink, or fragment not unique), TIMEOUT. Exit status:
0 all killed, 1 some survived, 2 invalid input, a failing baseline, or any
INVALID or TIMEOUT result, 3 no survivors but FAILED results needing judgment.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

_TAIL_LINES = 30


@dataclass(frozen=True)
class Mutant:
    id: str
    file: str
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
        missing = {"id", "file", "old", "new"} - entry.keys()
        if missing:
            raise ValueError(f"mutant {index} lacks {sorted(missing)}")
        unknown = entry.keys() - {"id", "file", "old", "new", "description"}
        if unknown:
            raise ValueError(f"mutant {index} has unknown keys {sorted(unknown)}")
        if not all(isinstance(value, str) for value in entry.values()):
            raise ValueError(f"mutant {index} values must be strings")
        if entry["id"] in seen:
            raise ValueError(f"duplicate mutant id {entry['id']!r}")
        if entry["old"] == entry["new"]:
            raise ValueError(f"mutant {entry['id']!r} does not change anything")
        if Path(entry["file"]).is_absolute() or ".." in Path(entry["file"]).parts:
            raise ValueError(f"mutant {entry['id']!r} file must be repository-relative")
        seen.add(entry["id"])
        mutants.append(Mutant(**entry))
    return mutants


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {args[0]} failed")
    return completed.stdout.strip()


def _run(command: str, cwd: Path, timeout: float) -> tuple[int | None, list[str]]:
    # Own process group, so a timeout also stops everything the command started.
    process = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        output += f"\ntimed out after {timeout:g}s"
        code = None
    else:
        code = process.returncode
    return code, [line for line in output.splitlines() if line.strip()]


def run_probes(
    mutants: list[Mutant],
    command: str,
    *,
    repo: Path,
    ref: str = "HEAD",
    timeout: float = 600.0,
    test_failure_codes: frozenset[int] = frozenset(),
) -> tuple[Outcome, list[Outcome]]:
    """Run the baseline and every mutant sequentially in a scratch worktree."""
    root = Path(_git(repo, "rev-parse", "--show-toplevel"))
    commit = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    with tempfile.TemporaryDirectory(prefix="probe-") as scratch:
        worktree = Path(scratch) / "tree"
        _git(root, "worktree", "add", "--detach", "--quiet", str(worktree), commit)
        try:
            code, lines = _run(command, worktree, timeout)
            baseline = Outcome(
                "baseline",
                "PASSED" if code == 0 else "FAILED",
                lines[-1] if lines else "",
                "",
                lines[-_TAIL_LINES:],
            )
            if code != 0:
                return baseline, []
            return baseline, [
                _probe(mutant, command, worktree, timeout, test_failure_codes)
                for mutant in mutants
            ]
        finally:
            _git(root, "worktree", "remove", "--force", str(worktree))


def _probe(
    mutant: Mutant,
    command: str,
    worktree: Path,
    timeout: float,
    test_failure_codes: frozenset[int],
) -> Outcome:
    # Resolve symlinks (of the file and its parents) and refuse anything that
    # leaves the scratch worktree, so a probe can never modify outside files.
    root = worktree.resolve()
    target = (worktree / mutant.file).resolve()
    if not target.is_relative_to(root):
        detail = "file resolves outside the repository (symlink)"
        return Outcome(mutant.id, "INVALID", detail, mutant.description)
    if not target.is_file():
        return Outcome(mutant.id, "INVALID", "file not found", mutant.description)
    original = target.read_bytes()
    source = original.decode("utf-8", errors="surrogateescape")
    count = source.count(mutant.old)
    if count != 1:
        detail = f"'old' occurs {count} times (expected 1)"
        return Outcome(mutant.id, "INVALID", detail, mutant.description)
    mutated = source.replace(mutant.old, mutant.new)
    target.write_bytes(mutated.encode("utf-8", errors="surrogateescape"))
    try:
        code, lines = _run(command, worktree, timeout)
    finally:
        target.write_bytes(original)
    if code is None:
        status = "TIMEOUT"
    elif code == 0:
        status = "SURVIVED"
    else:
        status = "KILLED" if code in test_failure_codes else "FAILED"
    return Outcome(
        mutant.id,
        status,
        lines[-1] if lines else "",
        mutant.description,
        lines[-_TAIL_LINES:],
    )


def _format(baseline: Outcome, outcomes: list[Outcome]) -> str:
    lines = [f"baseline: {baseline.status} ({baseline.detail})"]
    for outcome in outcomes:
        lines.append(f"{outcome.status:9} {outcome.id}: {outcome.description}")
        lines.append(f"          {outcome.detail}")
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    lines.append("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutants", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--json", type=Path, help="write results as JSON")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--test-failure-codes",
        default="",
        help="comma-separated exit codes that mean 'tests failed', e.g. 1",
    )
    parser.add_argument("command", nargs="+", help="test command after --")
    args = parser.parse_args(argv)
    try:
        codes = frozenset(
            int(code) for code in args.test_failure_codes.split(",") if code.strip()
        )
        mutants = load_mutants(args.mutants)
        baseline, outcomes = run_probes(
            mutants,
            shlex.join(args.command) if len(args.command) > 1 else args.command[0],
            repo=args.repo,
            ref=args.ref,
            timeout=args.timeout,
            test_failure_codes=codes,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"probe_files: {exc}", file=sys.stderr)
        return 2
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
    if statuses & {"INVALID", "TIMEOUT"}:
        return 2
    if "SURVIVED" in statuses:
        return 1
    return 3 if "FAILED" in statuses else 0


if __name__ == "__main__":
    sys.exit(main())
