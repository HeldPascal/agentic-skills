# Agentic Skills

Reusable Agent Skills for coding agents such as Codex and Claude Code.

## Skills

- [`orca-orchestrator`](skills/orca-orchestrator/SKILL.md) — adaptive multi-agent orchestration on top of Orca: spec-first task execution, role-separated Developer/Tester/Reviewer work with Junior/Senior levels, bounded autonomous recovery, evidence-based harness/model/locality routing, and persistent learned state outside the skill installation.

## Install

```bash
npx skills add HeldPascal/agentic-skills \
  --skill orca-orchestrator \
  --global \
  --agent codex \
  --agent claude-code
```

Update installed skills with:

```bash
npx skills update
```

Mutable configuration and learned runtime state deliberately live outside this repository (XDG config/state paths — see each skill's docs), so `npx skills update` can update skill logic without overwriting runtime experience.

## Development

Run tests for a skill's helper scripts with, e.g.:

```bash
python -m pytest skills/orca-orchestrator/tests
```

Repository-wide contribution guidance for coding agents lives in [`AGENTS.md`](AGENTS.md).
