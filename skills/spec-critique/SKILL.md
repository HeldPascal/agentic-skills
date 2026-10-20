---
name: spec-critique
description: Rigorously and independently critique a specification, design document, ADR, plan or other technical draft before anyone relies on it - completeness, consistency, testability, unnecessary prescription, downstream needs and fidelity to the stated intent. Use when asked to review or critique a draft spec/design/plan, when a draft (your own or another model's) should be checked before the user sees it, or as the critic in a spec author/critic dialogue.
---

# Spec critique

The goal is independent judgment, not agreement. A critique that only polishes wording has
failed; a critique that finds the ambiguity two implementers would resolve differently has
succeeded.

## Inputs

- **The draft** to critique.
- **The intent sources** the draft must honor: task brief, decision record, user statements,
  architectural constraints, parent specifications, existing code and conventions. Independence
  means independent *judgment*, not missing requirements - if the intent sources are not
  available, ask for them or state explicitly which ones you lacked.
- **The consumers** of the draft, if known: who builds on it (implementers, test writers,
  later work packages, operators).

## Method

1. **Expectations first.** Before reading the draft, read the intent sources and write down
   (for yourself) what the draft must settle: key decisions, interfaces, invariants, error
   behavior, edge cases, and the places where two competent people would most likely diverge.
   This baseline is what keeps the critique independent of the draft's framing.
2. **Read the draft against the baseline and the criteria below.** Verify claims where you can:
   recompute examples and golden values, check referenced code and APIs actually exist and
   behave as stated, run commands the draft says will work.
3. **Write findings** (format below), most important first.
4. **Iterate if in a dialogue:** on a revision, verify each change in the document itself, not
   in the author's summary. Accept well-reasoned rejections; push back where reasoning is weak.

## Criteria

| Criterion | Questions |
| --- | --- |
| Intent fidelity | Does anything contradict, weaken or silently trade away a stated user decision or constraint? A documented trade-off is still a contradiction - escalate it, do not accept it. |
| Completeness | Missing behavior, error cases, edge cases, invariants, failure and recovery semantics, interfaces others need? |
| Consistency | Internal contradictions; conflicts with parent specs, architecture, existing code or conventions? |
| Testability | Can each requirement be verified objectively? Could an isolated test writer and an isolated implementer converge without talking? Name concrete divergence risks ("both X and Y satisfy this sentence"). |
| Implementation freedom | Does it prescribe internals that are not part of the observable contract (call counts, helper structure, private data layout)? Over-specification inflates test suites and blocks good implementations. |
| Downstream needs | What will consumers need that is not stated: serialization and round trips, process boundaries (picklability), stable identities across machines/paths, error categories they must classify, extension points? |
| Readability | Can a cold reader understand it quickly? Prefer tables and lists over dense prose; reasonable length. |

## Findings format

Number each finding and tag its severity:

- **[BLOCKER]** - contradicts intent, is internally inconsistent, or makes correct work impossible.
- **[MAJOR]** - likely to cause divergent or wrong work, or a costly later revision.
- **[MINOR]** - worth fixing, low risk.

Each finding names the location, states the problem concretely, and proposes a resolution.
Mark findings that are **product-level decisions** (scope, user-visible behavior, intent
trade-offs) as `NEEDS_DECISION` - those go to the person who owns the intent, not to the author.
Briefly note what is sound, so the author knows what not to change.

End with a verdict: `ACCEPT` (no blocker/major left), `ACCEPT_WITH_FIXES`, or `REVISE`, plus any
open `NEEDS_DECISION` items.

## Standalone use

When critiquing a draft before a user sees it (e.g. a document another model just wrote),
return the findings and verdict to whoever revises the draft. If you revise it yourself, keep
the critique visible (as a short summary of what changed and why) rather than presenting a
silently "improved" draft, and still surface `NEEDS_DECISION` items to the user.
