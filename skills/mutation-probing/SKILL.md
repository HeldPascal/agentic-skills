---
name: mutation-probing
description: Find gaps in an existing test suite with a few targeted, hand-picked mutation probes - plausible defects injected one at a time to see whether the tests notice. Works for any language and test runner. Use when reviewing tests or a change, auditing test quality, or checking whether "all green" really means the behavior is verified. Not a full mutation-testing campaign.
metadata:
  version: "0.2.1"
---

# Mutation probing

A passing suite only proves that the tests pass. A mutation probe asks the sharper question:
*if this specific plausible bug existed, would any test fail?* A surviving probe is concrete,
reproducible evidence of a verification gap - usually more convincing than coverage numbers
or a reviewer's opinion.

This is a targeted audit technique, not exhaustive mutation testing. Use only enough probes to
investigate the component's highest-risk failure classes; no fixed count is required.

## Requires

- A git repository and the project's test command (whatever it is: `npm test`, `cargo test`,
  `go test ./...`, `make check`, `pytest`, ...).
- `python3` (3.11+) to run the bundled scripts.

Use the bundled harnesses or the manual procedure below; do not improvise another harness.

## 1. Choose probes from risk, not from syntax

Read the contract (spec, API docs, README) and the code under test, then ask: *which realistic
mistakes would a developer make here, and would they matter?* Good probe families:

- **State and history:** forget earlier entries (clear a cache or map after a lookup), reuse
  the first resolved object for every later request, share a counter between instances.
  Single-entity test fixtures hide these.
- **Value preservation:** drop or reset fields while passing a record through a stage (keep
  only the classification, lose measurements, metadata, provenance), convert values silently
  (integer vs. float, signed zero, precision, ordered vs. unordered collections).
- **Boundaries:** shift a limit by one (`<` vs `<=`, `max` vs `max + 1`), accept the first value
  outside a range, skip validation for one input class.
- **Error handling:** swallow an error, report it in another category, lose the original
  cause, convert interrupts or cancellation into ordinary errors, let a cleanup failure replace
  the original error.
- **Ordering and identity:** reverse an iteration, include an excluded field in a key or hash,
  drop a field from a key, reorder positional outputs.
- **Counting and accounting:** reset or skip a counter increment, count per attempt instead of
  per entity, stop a loop early or late.

Skip probes that are equivalent (no observable behavior change) or only reachable through
impossible states. Note them as equivalent if you considered them.

## 2. Run the probes

**Any language - `scripts/probe_files.py`.** Each mutant replaces one exact text fragment in
one file. The script creates a temporary detached git worktree of the committed state, runs the
test command once unmutated (baseline), then for every mutant applies the replacement, runs the
command and restores the file. Your working tree is never touched; the scratch worktree is
removed afterwards.

```bash
# mutants.json: [{"id": "M1", "file": "src/runner.ts", "old": "<exact fragment>",
#                 "new": "<replacement>", "description": "forget instance history"}]
python3 <skill-dir>/scripts/probe_files.py --mutants mutants.json --json probes.json \
    --test-failure-codes 1 -- npm test -- tests/runner
```

- The fragment must occur exactly once in the file; widen it until it is unique.
- It probes the committed state (`--ref`, default `HEAD`): commit what you want to probe.
- The test command runs in a fresh checkout: dependencies or build steps that live outside the
  repository (virtual environments, `node_modules`, build caches) must be created by the
  command or already be shareable. Select a narrow test subset to keep runs fast.
- A nonzero exit is not automatically detection - the mutation may only break the build or
  test discovery. Where the runner uses a distinct exit code for failing tests, pass it with
  `--test-failure-codes` (e.g. pytest: `1`; `2` means collection or usage errors). Many runners
  (e.g. `cargo test`, `go test`) use the same code for build and test failures - then leave it
  out and judge every `FAILED` result from its output tail.
- Statuses: `KILLED` (exit code listed as a test failure), `FAILED` (any other nonzero exit -
  judge from the output tail whether a test caught the defect or the run broke; report it as
  such, not as a kill), `SURVIVED` (gap), `INVALID` (file missing, resolving outside the
  repository through a symlink, or fragment not unique), `TIMEOUT`. Exit status: 0 all killed,
  1 some survived, 2 invalid input, failing baseline, or any `INVALID`/`TIMEOUT`, 3 nothing
  survived but `FAILED` results need judgment.

**Python with pytest - faster in-process harness.** For Python projects tested with pytest,
`scripts/probe_pytest.py` applies mutations in memory without a checkout per run. Read
`references/python-pytest.md` before using it; it has limitations (subprocesses run unmutated)
that decide which harness fits.

**Manual procedure** (only if neither script fits, e.g. no git): copy the project to a scratch
location, apply one mutation, run the tests, record the result, restore, repeat. Never mutate
the working tree you are reviewing.

## 3. Report

For each surviving probe report:

1. The probe (file or module, fragment, replacement) and the plausible defect it represents.
2. Why it matters (which contract clause or downstream behavior it would break).
3. The smallest test change that would kill it - preferably strengthening or parametrizing an
   existing test rather than adding a new one.

Also list killed probes briefly (they document what *is* verified) and equivalent probes you
skipped, and give the mutants file so the probes can be re-run. Treat the result as diagnostic
evidence about the suite, not as a score: a killed probe does not prove the test is good, and a
survivor is not automatically a defect in the production code.

When tests are added in response, re-run the same probes to confirm they are now killed.
