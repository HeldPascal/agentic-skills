#!/usr/bin/env python3
"""Check that a git worktree really sits on the intended baseline.

Catches the situations that silently derail delegated work: a worktree
created from a stale ref (e.g. the remote branch while the local branch holds
newer commits), a HEAD that differs from the agreed baseline commit, and
uncommitted changes.

Usage:
    check_baseline.py --worktree PATH [--expect REF] [--base BRANCH]

``--expect`` requires HEAD to equal REF. ``--base`` requires HEAD to contain
every commit of the local BRANCH and reports how BRANCH relates to its
upstream. Untracked files count as changes regardless of the user's
``status.showUntrackedFiles`` setting; ignored files do not. Exit status 0 means all checks passed, 1 means a problem was found,
2 means the inputs could not be evaluated.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(worktree: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(worktree), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GitError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _count(worktree: Path, revision_range: str) -> int:
    return int(git(worktree, "rev-list", "--count", revision_range))


def check(
    worktree: Path, expect: str | None = None, base: str | None = None
) -> tuple[list[str], list[str]]:
    """Return (facts, problems) describing the worktree state."""
    facts: list[str] = []
    problems: list[str] = []
    head = git(worktree, "rev-parse", "HEAD")
    branch = git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    facts.append(f"HEAD {head[:12]} on {branch}")

    status = git(worktree, "status", "--porcelain", "--untracked-files=all")
    if status:
        changed = len(status.splitlines())
        problems.append(f"working tree has {changed} uncommitted change(s)")

    if expect is not None:
        expected = git(worktree, "rev-parse", "--verify", f"{expect}^{{commit}}")
        if expected != head:
            problems.append(
                f"HEAD {head[:12]} differs from expected baseline "
                f"{expect} ({expected[:12]})"
            )
        else:
            facts.append(f"HEAD equals expected baseline {expect}")

    if base is not None:
        git(worktree, "rev-parse", "--verify", f"refs/heads/{base}")
        missing = _count(worktree, f"HEAD..{base}")
        if missing:
            problems.append(
                f"HEAD lacks {missing} commit(s) of local {base} - "
                "the worktree may be based on a stale ref"
            )
        else:
            facts.append(f"HEAD contains local {base}")
        try:
            upstream = git(
                worktree, "rev-parse", "--abbrev-ref", f"{base}@{{upstream}}"
            )
        except GitError:
            facts.append(f"local {base} has no upstream")
        else:
            ahead = _count(worktree, f"{upstream}..{base}")
            behind = _count(worktree, f"{base}..{upstream}")
            facts.append(f"local {base} is {ahead} ahead / {behind} behind {upstream}")
    return facts, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--expect", help="commit or ref HEAD must equal")
    parser.add_argument("--base", help="local branch HEAD must contain")
    args = parser.parse_args(argv)
    try:
        facts, problems = check(args.worktree, args.expect, args.base)
    except GitError as exc:
        print(f"check_baseline: {exc}", file=sys.stderr)
        return 2
    for fact in facts:
        print(f"ok:      {fact}")
    for problem in problems:
        print(f"PROBLEM: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
