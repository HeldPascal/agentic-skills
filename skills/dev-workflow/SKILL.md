---
name: dev-workflow
description: Spec-first, multi-agent software development workflow - a coordinator runs requirements discovery, spec author/critic dialogue, independently developed tests and implementation, integration with failure classification, cross-model code and test review, and evidence-based completion. Use when coordinating a non-trivial feature or milestone through several agents (e.g. with Orca), or when you were dispatched as one of its roles (spec author/critic, test author, implementer, code or test reviewer).
metadata:
  version: "0.3.1"
---

# Development workflow

A coordinator turns a user request into accepted specifications, has tests and implementation
developed independently against them, integrates and verifies the result, gets it reviewed by a
different model family, and repairs what review finds - all with evidence, not claims.

```
discovery -> decomposition -> per work package:
  spec (author <-> critic) -> baseline -> tests || implementation -> integration
  -> cross-model review (code || tests) -> repair -> accepted
-> final verification and report
```

## Find your role

Read the shared rules below, then **only** the file for your role. Do not read other roles'
files unless your role file tells you to.

| Role | File | Also uses |
| --- | --- | --- |
| Coordinator | `roles/coordinator.md` | `references/orca.md` (on Orca), skills `requirements-discovery`, `spec-critique` |
| Spec Author | `roles/spec-author.md` | - |
| Spec Critic | `roles/spec-critic.md` | skill `spec-critique` |
| Test Author | `roles/test-author.md` | `references/testing.md` |
| Implementer | `roles/implementer.md` | - |
| Code Reviewer | `roles/reviewer-code.md` | skill `mutation-probing` |
| Test Reviewer | `roles/reviewer-tests.md` | `references/testing.md`, skill `mutation-probing` |

Paths are relative to this skill's directory. A dispatched worker's start prompt names its
role, its mode and the skills to load.

## Requires

- Skills: `requirements-discovery`, `spec-critique` and `mutation-probing` (same repository,
  installed together with this one) for every agent harness that receives work; on Orca also
  Orca's `orchestration` skill.
- Tools: `git`; `python3` (3.11+) to run the helper scripts - the project itself can use any
  language and toolchain.
- The coordinator verifies all of this with `scripts/check_requirements.py` before dispatching.

## Authority of intent

```
current user decisions and project constraints
  -> task brief / decision record
    -> accepted specification
      -> tests and implementation
```

Anyone may challenge an earlier level and propose alternatives, but nobody silently overrides
it. A conflict with a higher level is raised (`NEEDS_DECISION` or a question to the
coordinator), not resolved by quietly adapting. Never change a specification merely to make an
incorrect implementation or test pass.

## Shared rules for every role

1. **Scope.** Do only the assigned work, inside the paths you own. Need something outside it
   (another file, a dependency change, a spec change)? Ask the coordinator.
2. **Independence when assigned.** If your assignment lists isolation rules, do not read,
   diff, check out or search the listed worktrees, branches or artifacts. Worktrees are not a
   security boundary - the rule is yours to keep. If you break it accidentally, say so in your
   report.
3. **Evidence.** Never claim a check passed unless you ran it. Report the commands you ran
   and their actual results. Unverifiable means unverified.
4. **Ambiguity.** Do not guess silently. Ask the coordinator through your orchestration
   channel, citing the document section; if you must proceed, record the assumption in your
   report. Never open an interactive prompt nobody can answer.
5. **Bounded effort.** A failed attempt is a valid result. If you notice you are repeating an
   approach without new information, stop and report what you tried, the concrete failure,
   and what you believe must change.
6. **Repository conventions.** Follow the project's existing tooling, style, git
   configuration and commit conventions. Commit only where your role says so, on your own
   branch; never push, merge into shared branches, or change git configuration.
7. **Communication.** Agent-to-agent messages, specifications, code, comments and tests in
   English (unless the repository does otherwise). Be concise and specific.
8. **Missing dependencies.** If a skill, tool or document you are told to use is not
   available, do not recreate it from memory or improvise a substitute - stop and report it.
   Use a fallback only where the instructions name one explicitly.
9. **Completion.** End with exactly one completion report through your orchestration channel,
   marked succeeded or failed (never hide failure in prose), naming the files you changed and
   your report file if any. Then stop.
