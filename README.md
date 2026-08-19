# Agentic Skills

Reusable Agent Skills for coding agents such as Codex and Claude Code.

## Skills

### `orca-orchestrator`

Adaptive multi-agent orchestration on top of Orca. The skill coordinates spec-first work, Junior/Senior review loops, and evidence-based harness/model routing while keeping mutable learned state outside the skill installation.

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

## Repository layout

```text
skills/
└── orca-orchestrator/
    ├── SKILL.md
    ├── references/
    ├── scripts/
    └── tests/
```

Mutable configuration and learned state deliberately live outside this repository.
