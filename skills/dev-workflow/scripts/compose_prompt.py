#!/usr/bin/env python3
"""Compose a worker start prompt from the dev-workflow skill and a context file.

The prompt is rendered fresh from structured fields on every dispatch, so no
text is copied over from earlier prompts. It points the worker at the shared
rules and its role file (absolute paths of this skill installation), lists the
task context, and states coordinator overrides together with their reasons.

Usage:
    compose_prompt.py --describe --role ROLE [--mode MODE]
    compose_prompt.py --role ROLE --context ctx.json [--set KEY=VALUE ...]
                      --out prompt.md

``--describe`` lists the required and optional context fields of a role and
mode. The context file is a JSON object; ``--set`` overrides single fields for
one dispatch (list fields take a JSON list), so contexts never need to be
edited by hand. The result is validated as a whole:

- relative paths are resolved against ``workspace`` and rendered absolute;
  listed input documents must exist as files (catches stale references);
- spec roles need intent sources, independent workers need ownership and
  isolation, spec changes need the change and its reason;
- with a ``baseline``, ``workspace`` must be the root of a git worktree whose
  HEAD is exactly that commit, so a worker cannot start in the wrong place.

On success the script prints one JSON line with the prompt path and the
resolved workspace; dispatch the worker into exactly that workspace.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]

ROLES = {
    "spec-author": ("Specification Author", ("initial", "revision")),
    "spec-critic": ("Specification Critic", ("initial", "delta-review")),
    "test-author": ("Test Author", ("initial", "repair")),
    "implementer": ("Implementer", ("initial", "repair")),
    "reviewer-code": ("Code Reviewer", ("review",)),
    "reviewer-tests": ("Test Reviewer", ("review",)),
}

# Keys that every context needs, plus per-role additions.
COMMON_REQUIRED = ("work_package", "task", "workspace", "agent")

# How each harness is told to load a skill by name. Other harnesses get the
# skill's file path in this installation instead.
SKILL_SYNTAX = {
    "claude": "load the skill `{name}` with your Skill tool",
    "codex": "use the skill `${name}`",
}
# Standalone skills a role's method depends on (dev-workflow itself is implied).
ROLE_SKILLS = {
    "spec-critic": ("spec-critique",),
    "reviewer-code": ("mutation-probing",),
    "reviewer-tests": ("mutation-probing",),
}
ROLE_REQUIRED = {
    "spec-author": ("spec", "intent"),
    "spec-critic": ("spec", "intent"),
    "test-author": ("spec", "baseline", "report"),
    "implementer": ("spec", "baseline"),
    "reviewer-code": ("spec", "diff", "report"),
    "reviewer-tests": ("spec", "diff", "report"),
}
MODE_REQUIRED = {
    ("spec-author", "revision"): ("change", "change_reason"),
    ("spec-critic", "delta-review"): ("change", "change_reason"),
    ("test-author", "initial"): ("ownership", "isolation"),
    ("test-author", "repair"): ("ownership",),
    ("implementer", "initial"): ("ownership", "isolation"),
    ("implementer", "repair"): ("ownership",),
}

# key -> (label, kind). kind: "str", "docs" (list of existing files), "path"
# (file that may not exist yet), "list" (free-form strings), "overrides".
FIELDS = {
    "work_package": ("Work package", "str"),
    "agent": ("Agent harness", "str"),
    "task": ("Assignment", "str"),
    "workspace": ("Workspace", "str"),
    "mode": ("Mode", "str"),
    "spec": ("Specification", "path"),
    "intent": ("Intent sources (task brief, decisions, constraints)", "docs"),
    "references": ("Further references", "docs"),
    "baseline": ("Baseline commit", "str"),
    "diff": ("Changes under review", "str"),
    "change": ("Proposed specification change", "str"),
    "change_reason": ("Reason for the change", "str"),
    "report": ("Write your report to", "path"),
    "ownership": ("You may edit only", "list"),
    "isolation": ("Do not access", "list"),
    "checks": ("Checks to run", "list"),
    "constraints": ("Constraints", "list"),
    "peers": ("Peers", "list"),
    "overrides": ("Coordinator overrides", "overrides"),
}


class ContextError(ValueError):
    pass


def _check_type(key: str, value: object, kind: str) -> None:
    if kind in {"str", "path"}:
        if not isinstance(value, str) or not value.strip():
            raise ContextError(f"{key} must be a nonempty string")
    elif kind in {"docs", "list"}:
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ContextError(f"{key} must be a list of nonempty strings")
    elif kind == "overrides":
        if not isinstance(value, list):
            raise ContextError("overrides must be a list")
        for index, item in enumerate(value):
            if (
                not isinstance(item, dict)
                or set(item) != {"instruction", "reason"}
                or not all(isinstance(v, str) and v.strip() for v in item.values())
            ):
                raise ContextError(
                    f"overrides[{index}] needs exactly a nonempty "
                    "'instruction' and 'reason'"
                )


def validate(role: str, context: dict) -> dict:
    """Validate a context for a role; return it with mode and absolute paths."""
    if role not in ROLES:
        raise ContextError(f"unknown role {role!r}; choose from {sorted(ROLES)}")
    if not isinstance(context, dict):
        raise ContextError("context must be a JSON object")
    unknown = set(context) - set(FIELDS)
    if unknown:
        raise ContextError(f"unknown context keys {sorted(unknown)}")
    for key, value in context.items():
        _check_type(key, value, FIELDS[key][1])
    modes = ROLES[role][1]
    mode = context.get("mode", modes[0])
    if mode not in modes:
        raise ContextError(f"{role} mode must be one of {list(modes)}")
    required = (
        COMMON_REQUIRED + ROLE_REQUIRED[role] + MODE_REQUIRED.get((role, mode), ())
    )
    missing = [key for key in required if key not in context or context[key] == []]
    if missing:
        raise ContextError(f"{role} ({mode}) context lacks or has empty {missing}")

    if context["agent"] not in (*SKILL_SYNTAX, "other"):
        raise ContextError(f"agent must be one of {[*SKILL_SYNTAX, 'other']}")
    if context["agent"] == "other":
        for name in ("dev-workflow", *ROLE_SKILLS.get(role, ())):
            if not (SKILL_DIR.parent / name / "SKILL.md").is_file():
                raise ContextError(
                    f"skill {name} is not installed next to dev-workflow"
                )

    workspace = Path(context["workspace"]).expanduser().resolve()
    if not workspace.is_dir():
        raise ContextError(f"workspace {workspace} is not a directory")
    if "baseline" in context:
        _check_workspace_baseline(workspace, context["baseline"])
    resolved = {**context, "mode": mode, "workspace": str(workspace)}
    for key, (_, kind) in FIELDS.items():
        if key in context and kind == "path":
            resolved[key] = str(workspace / Path(context[key]).expanduser())
        elif key in context and kind == "docs":
            resolved[key] = [
                str(workspace / Path(d).expanduser()) for d in context[key]
            ]
    documents = list(resolved.get("intent", [])) + list(resolved.get("references", []))
    # Author and critic start together before the draft exists.
    if (role, mode) not in {("spec-author", "initial"), ("spec-critic", "initial")}:
        documents.append(resolved["spec"])
    for document in documents:
        if not Path(document).is_file():
            raise ContextError(f"referenced document is not a file: {document}")
    return resolved


def _git(workspace: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ContextError(
            f"git {' '.join(args)} failed in {workspace}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _check_workspace_baseline(workspace: Path, baseline: str) -> None:
    top = Path(_git(workspace, "rev-parse", "--show-toplevel")).resolve()
    if top != workspace:
        raise ContextError(f"workspace {workspace} is not the root of a git worktree")
    head = _git(workspace, "rev-parse", "HEAD")
    expected = _git(workspace, "rev-parse", "--verify", f"{baseline}^{{commit}}")
    if head != expected:
        raise ContextError(
            f"workspace HEAD {head[:12]} does not match baseline {baseline} "
            f"({expected[:12]})"
        )


def apply_sets(context: dict, assignments: list[str]) -> dict:
    """Return a copy of context with KEY=VALUE assignments applied."""
    updated = dict(context)
    for assignment in assignments:
        key, sep, value = assignment.partition("=")
        if not sep or key not in FIELDS:
            raise ContextError(
                f"--set expects KEY=VALUE with a known key: {assignment!r}"
            )
        if FIELDS[key][1] in {"docs", "list", "overrides"}:
            try:
                updated[key] = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ContextError(f"--set {key} needs a JSON list: {exc}") from exc
        else:
            updated[key] = value
    return updated


def describe(role: str, mode: str | None = None) -> str:
    """Describe the context fields a role (and mode) requires and accepts."""
    if role not in ROLES:
        raise ContextError(f"unknown role {role!r}; choose from {sorted(ROLES)}")
    modes = ROLES[role][1]
    mode = mode or modes[0]
    if mode not in modes:
        raise ContextError(f"{role} mode must be one of {list(modes)}")
    required = (
        COMMON_REQUIRED + ROLE_REQUIRED[role] + MODE_REQUIRED.get((role, mode), ())
    )
    lines = [f"{role} (mode {mode}; modes: {', '.join(modes)})", "required:"]
    lines += [f"  {key:14} {FIELDS[key][1]:9} {FIELDS[key][0]}" for key in required]
    lines.append("optional:")
    lines += [
        f"  {key:14} {kind:9} {label}"
        for key, (label, kind) in FIELDS.items()
        if key not in required
    ]
    lines.append(f"agent: one of {[*SKILL_SYNTAX, 'other']}")
    return "\n".join(lines)


def _load(name: str, agent: str) -> str:
    if agent in SKILL_SYNTAX:
        return SKILL_SYNTAX[agent].format(name=name)
    return f"read {SKILL_DIR.parent / name / 'SKILL.md'}"


def _skill_instructions(role: str, context: dict) -> list[str]:
    agent, mode = context["agent"], context["mode"]
    first = _load("dev-workflow", agent)
    lines = [
        (
            f"1. {first[0].upper()}{first[1:]}; read its shared rules (SKILL.md) "
            f"and `roles/{role}.md` (your role; mode: {mode}) completely and "
            "follow them."
        ),
    ]
    for index, name in enumerate(ROLE_SKILLS.get(role, ()), start=2):
        lines.append(f"{index}. Your role uses this skill: {_load(name, agent)}.")
    lines.append(
        "If a skill named here is not available to you, stop and report that "
        "through your orchestration channel - do not recreate it from memory."
    )
    return lines


def render(role: str, context: dict) -> str:
    """Render the worker prompt for an already validated context."""
    title, _ = ROLES[role]
    lines = [
        f"# {title} - {context['work_package']} (dev-workflow, mode: {context['mode']})",
        "",
        "Before doing anything else:",
        *_skill_instructions(role, context),
        "",
        "## Assignment",
        "",
        context["task"].strip(),
        "",
        "## Context",
        "",
    ]
    for key, (label, kind) in FIELDS.items():
        if (
            key in {"task", "mode", "overrides", "work_package", "agent"}
            or key not in context
        ):
            continue
        value = context[key]
        if kind in {"docs", "list"}:
            lines.append(f"- {label}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"- {label}: {value}")
    lines += ["", "## Coordinator overrides", ""]
    overrides = context.get("overrides", [])
    if overrides:
        for index, item in enumerate(overrides, start=1):
            lines.append(
                f"{index}. {item['instruction'].strip()} "
                f"(reason: {item['reason'].strip()})"
            )
        lines += [
            "",
            (
                "If an override conflicts with the specification, a recorded user "
                "decision or the shared rules, do not follow it silently - ask the "
                "coordinator."
            ),
        ]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--role", required=True, choices=sorted(ROLES))
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--mode", help="with --describe: the mode to describe")
    parser.add_argument("--context", type=Path)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.describe:
            print(describe(args.role, args.mode))
            return 0
        if args.context is None or args.out is None:
            raise ContextError("--context and --out are required (or use --describe)")
        context = json.loads(args.context.read_text(encoding="utf-8"))
        if not isinstance(context, dict):
            raise ContextError("context must be a JSON object")
        validated = validate(args.role, apply_sets(context, args.set))
    except (OSError, json.JSONDecodeError, ContextError) as exc:
        print(f"compose_prompt: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(args.role, validated), encoding="utf-8")
    print(
        json.dumps(
            {
                "prompt": str(args.out.resolve()),
                "workspace": validated["workspace"],
                "role": args.role,
                "mode": validated["mode"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
