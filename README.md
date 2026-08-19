# Agentic Skills

Reusable Agent Skills for coding agents such as Codex and Claude Code.

## Skills

### `orca-orchestrator`

Adaptive multi-agent orchestration on top of Orca. The skill coordinates:

- spec-first task execution,
- Junior/Senior review and rework loops,
- bounded autonomous recovery,
- independent review and takeover verification,
- evidence-based harness/model routing,
- persistent learned state outside the skill installation.

Install globally for Codex and Claude Code:

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

The skill follows XDG paths with fallbacks:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/orca-orchestrator/
${XDG_STATE_HOME:-$HOME/.local/state}/orca-orchestrator/
```

Initialize the local state after installation:

```bash
python ~/.agents/skills/orca-orchestrator/scripts/state.py init
```

The exact installed path may differ by agent/symlink layout; invoke the helper from the installed skill directory you use.

## Repository layout

```text
skills/
└── orca-orchestrator/
    ├── SKILL.md
    ├── references/
    │   ├── workflow.md
    │   ├── routing.md
    │   ├── guardrails.md
    │   └── state.md
    ├── scripts/
    │   ├── state.py
    │   ├── discover.py
    │   └── doctor.py
    └── tests/
```

Mutable configuration and learned state deliberately live outside this repository, so `npx skills update` can update skill logic without overwriting runtime experience.

## State layers

The orchestrator keeps evidence separate from beliefs:

```text
raw observations
      ↓
deterministic aggregates
      ↓
qualitative registry beliefs
      ↓
routing decisions
```

Older raw observations may be deterministically archived when active-history thresholds are exceeded. They remain available for audit/debugging and continue to contribute to aggregates.

## Development

Run the state-helper tests with:

```bash
python -m pytest skills/orca-orchestrator/tests
```

Repository-wide contribution guidance for coding agents lives in [`AGENTS.md`](AGENTS.md).
