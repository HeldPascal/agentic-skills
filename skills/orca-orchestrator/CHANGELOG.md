# Changelog

All notable changes to the `orca-orchestrator` skill are documented here. This skill's `version` (in `SKILL.md` frontmatter) follows [Semantic Versioning](https://semver.org/): breaking changes to the state/config schema or the skill's behavioral contract bump the major version, additive changes bump the minor version, and clarifications/fixes bump the patch version.

## 0.3.0

- Split execution into separate Developer/Tester/Reviewer roles (orthogonal to Junior/Senior level), with isolated contexts and an explicit intra-role vs. cross-role review distinction.
- Added `role`, `host`, and `effort` as explicit observation/routing dimensions; the combination key used for aggregates/registry grouping is now `harness|model|backend|effort` instead of `harness|model|backend`.
- Made `discover.py` report a heuristic cloud-auth signal and known effort levels per harness, in addition to local tool/backend discovery, and documented discovery cadence.
- Made calling `task.py`/`state.py` at task start/record/finish a hard requirement in the workflow text, not a soft recommendation.
- Trimmed the repository README to a skill index; removed the skill-specific repository layout tree from it.

## 0.2.0

- Added `scripts/task.py` for deterministic per-task guardrail counters (dispatches, rework rounds, spec revisions, technical retries, blocking timeouts), replacing LLM self-tracking of limits.
- Added deterministic observation compaction/archiving and rebuildable aggregates in `scripts/state.py`.
- Documented bounded-autonomy guardrails (rework/spec/dispatch/elapsed-time limits, reviewer independence fallback, `TAKE_OVER` closure).

## 0.1.0

- Initial skill: spec-first workflow, Junior/Senior execution and review loop, adaptive harness/model routing, XDG-based config/state layout, local capability discovery, and the `state.py` helper (`init`/`observe`/`show`/`aggregate`).
