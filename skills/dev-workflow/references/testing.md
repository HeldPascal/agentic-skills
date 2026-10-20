# Testing philosophy

Shared by Test Author and Test Reviewer. The objective is **high confidence and strong fault
detection**, not a high test count or coverage percentage.

## Risk-based design

1. From the specification, list the plausible ways this component could be wrong - the failure
   classes. Include the contract's edge cases and error behavior, and the risks of how the
   component is used downstream.
2. Choose techniques by expected value: unit tests for contracts, integration tests at real
   boundaries (storage, processes, other packages), a few end-to-end scenarios for user-facing
   behavior, property-style or metamorphic checks where exact outputs are hard to state,
   golden values for anything that must stay stable.
3. Pick a compact set of cases that covers the failure classes; parametrize a class of inputs in
   one readable table with descriptive ids rather than writing near-duplicate tests or
   exhaustive cross-products of equivalent inputs.

## Known recurring gaps

These kept slipping past otherwise strong suites. Consider them wherever the design makes them
relevant - they are review heuristics, not mandatory tests for every component:

- **State and routing hidden by single-entity fixtures.** Components that keep history, caches,
  registries or route requests need scenarios with several interleaved entities (A, B, A; two
  systems; two keys in one store), including failure of one next to success of another.
- **Values lost or changed between stages.** When data passes through validation, conversion,
  orchestration or persistence, assert the full values that arrive downstream - not only counts
  or a classification - and compare type-sensitively where `True`, `1`, `1.0` or `-0.0` and
  `0.0` could be confused.
- **Only-positive equality.** Where values must differ, test inequality too.
- **Error propagation details.** Exception category, identity and cause chain; interrupts
  (`KeyboardInterrupt`, `SystemExit`) passing through unchanged; cleanup failures not masking
  the original error.

## Quality

Tests should be readable and self-documenting (clear names, arrange/act/assert), behavior- and
contract-focused, deterministic, and resistant to irrelevant implementation changes. Avoid:
redundant tests, excessive mocking, complicated fixtures that hide which values matter,
assertions that do not verify behavior, tests that re-implement the production logic, and
coupling to details the specification does not promise (private helpers, exact prose beyond
what the spec guarantees, platform-specific types).

## Evidence

- **Red-first** against a skeleton or the old behavior shows tests can fail for the right
  reason; it does not prove completeness.
- **Coverage** (branch coverage preferred) is diagnostic: investigate uncovered behavior by risk,
  do not optimize the number.
- **Mutation probes** by an independent reviewer are the strongest evidence that the suite
  detects realistic defects (see the `mutation-probing` skill).
