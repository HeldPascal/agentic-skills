# Agentic Skills

Reusable Agent Skills for coding agents such as Codex and Claude Code.

## Skills

- [`dev-workflow`](skills/dev-workflow/SKILL.md) — spec-first multi-agent development workflow: a coordinator runs discovery, a spec author/critic dialogue, independently developed tests and implementation, integration with failure classification, cross-model code and test review, and evidence-based completion. Role files per agent; Orca mechanics in a separate reference.
- [`requirements-discovery`](skills/requirements-discovery/SKILL.md) — turn a vague request into a Task Brief and a lightweight Decision Record through focused questions.
- [`spec-critique`](skills/spec-critique/SKILL.md) — independent, rigorous critique of specifications, designs and drafts (also usable on a model's draft before the user sees it).
- [`mutation-probing`](skills/mutation-probing/SKILL.md) — targeted mutation probes that show whether a test suite catches plausible defects; language-agnostic harness (scratch git worktree, any test command) plus a faster in-process harness for Python/pytest.
- [`orca-orchestrator`](skills/orca-orchestrator/SKILL.md) — **deprecated**, superseded by `dev-workflow`; kept until the new workflow has proven itself on a real task, then removed.

## Install

```bash
npx skills add HeldPascal/agentic-skills \
  --skill dev-workflow --skill requirements-discovery \
  --skill spec-critique --skill mutation-probing \
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
uvx --with pytest --from pytest pytest -q skills/dev-workflow/tests skills/mutation-probing/tests
```

Repository-wide contribution guidance for coding agents lives in [`AGENTS.md`](AGENTS.md).
