# AGENTS.md

This repository contains reusable Agent Skills.

## Conventions

- Keep each skill self-contained below `skills/<skill-name>/`.
- Keep `SKILL.md` portable across compatible agents; avoid agent-specific frontmatter unless strictly necessary.
- Put detailed guidance in `references/` and executable helpers in `scripts/`.
- Keep mutable user configuration and learned runtime state outside the repository.
- Prefer small, auditable scripts with tests over instructions that ask an LLM to edit structured state directly.
- Do not hard-code transient model or harness rankings into skills. Store observations and learned preferences in runtime state.
- Preserve the distinction between raw observations, deterministic aggregates, and qualitative routing beliefs.
- Never discard raw observation evidence during compaction; archive it outside the normal loading path instead.
- Do not introduce hidden routing scores without a clear, auditable reason. Prefer explicit metrics plus task-context reasoning.
- Keep autonomous recovery bounded. Changes to rework/spec/dispatch/time limits must remain configurable rather than embedded as model-specific behavior.
- Maintain backward compatibility with existing compatible state/config files when adding defaults. Bump/migrate the schema deliberately when compatibility cannot be preserved.

## Development checks

For changes to `orca-orchestrator` state helpers, run:

```bash
python -m pytest skills/orca-orchestrator/tests
```

The helper scripts should remain standard-library-only unless a dependency provides a clear benefit that justifies installation/runtime complexity.

When changing workflow policy, update the relevant reference document and keep `SKILL.md` focused on the portable high-level contract instead of duplicating every detail.
