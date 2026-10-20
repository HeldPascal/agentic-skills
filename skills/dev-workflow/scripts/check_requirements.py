#!/usr/bin/env python3
"""Check that the skills and tools the workflow depends on are available.

Run by the coordinator during setup, before any dispatch. For every agent
harness that will receive work it looks for the required skills in the
directories that harness actually loads skills from, and it checks the
command-line tools the workflow uses. Missing pieces are reported so they can
be installed - agents must not improvise substitutes.

Usage:
    check_requirements.py --agent claude --agent codex [--orca]
                          [--workspace DIR] [--skills-dir AGENT=DIR ...]

``--skills-dir`` adds a skill directory for an agent (e.g. a plugin location
this script does not know). Exit status 0 when everything was found, 1 when
something is missing.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKFLOW_SKILLS = (
    "dev-workflow",
    "requirements-discovery",
    "spec-critique",
    "mutation-probing",
)
ORCA_SKILLS = ("orchestration",)
TOOLS = ("git", "python3")


def skill_dirs(agent: str, workspace: Path) -> list[Path]:
    """Directories the given harness loads skills from, most specific first."""
    home = Path.home()
    if agent == "claude":
        dirs = [workspace / ".claude" / "skills"]
        config = os.environ.get("CLAUDE_CONFIG_DIR")
        if config:
            dirs.append(Path(config) / "skills")
        dirs.append(home / ".claude" / "skills")
        return dirs
    if agent == "codex":
        codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
        return [
            workspace / ".agents" / "skills",
            home / ".agents" / "skills",
            codex_home / "skills",
        ]
    return []


def _declared_name(skill_file: Path) -> str | None:
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


def find_skill(name: str, dirs: list[Path]) -> Path | None:
    """Return the SKILL.md of ``name`` in the first directory that has it."""
    for directory in dirs:
        candidate = directory / name / "SKILL.md"
        if candidate.is_file() and _declared_name(candidate) == name:
            return candidate
    return None


def check(
    agents: list[str],
    workspace: Path,
    orca: bool,
    extra_dirs: dict[str, list[Path]],
) -> tuple[list[str], list[str]]:
    """Return (facts, problems)."""
    facts: list[str] = []
    problems: list[str] = []
    for tool in TOOLS + (("orca",) if orca else ()):
        location = shutil.which(tool)
        if location:
            facts.append(f"tool {tool}: {location}")
        else:
            problems.append(f"tool {tool} not found on PATH")

    required = WORKFLOW_SKILLS + (ORCA_SKILLS if orca else ())
    for agent in agents:
        dirs = extra_dirs.get(agent, []) + skill_dirs(agent, workspace)
        if not dirs:
            problems.append(
                f"{agent}: unknown harness - pass its skill directory "
                f"with --skills-dir {agent}=DIR"
            )
            continue
        for name in required:
            found = find_skill(name, dirs)
            if found:
                facts.append(f"{agent}: skill {name} at {found.parent}")
            else:
                problems.append(
                    f"{agent}: skill {name} not found in "
                    + ", ".join(str(d) for d in dirs)
                )

    if orca and shutil.which("orca"):
        completed = subprocess.run(
            ["orca", "skills", "get", "orchestration"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            facts.append("orca: version-matched orchestration guide available")
        else:
            problems.append(
                "orca: `orca skills get orchestration` failed - update Orca"
            )
    return facts, problems


def _parse_dirs(values: list[str]) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for value in values:
        agent, sep, directory = value.partition("=")
        if not sep or not agent or not directory:
            raise ValueError(f"--skills-dir expects AGENT=DIR, got {value!r}")
        result.setdefault(agent, []).append(Path(directory).expanduser())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", action="append", required=True)
    parser.add_argument("--orca", action="store_true", help="also require Orca")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--skills-dir", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        extra = _parse_dirs(args.skills_dir)
    except ValueError as exc:
        print(f"check_requirements: {exc}", file=sys.stderr)
        return 2
    facts, problems = check(args.agent, args.workspace.resolve(), args.orca, extra)
    for fact in facts:
        print(f"ok:      {fact}")
    for problem in problems:
        print(f"MISSING: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
