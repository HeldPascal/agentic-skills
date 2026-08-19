# AGENTS.md

This repository contains reusable Agent Skills.

## Conventions

- Keep each skill self-contained below `skills/<skill-name>/`.
- Keep `SKILL.md` portable across compatible agents; avoid agent-specific frontmatter unless strictly necessary.
- Put detailed guidance in `references/` and executable helpers in `scripts/`.
- Keep mutable user configuration and learned runtime state outside the repository.
- Prefer small, auditable scripts with tests over instructions that ask an LLM to edit structured state directly.
- Do not hard-code transient model or harness rankings into skills. Store observations and learned preferences in runtime state.
