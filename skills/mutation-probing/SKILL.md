---
name: mutation-probing
description: Find gaps in an existing test suite with a few targeted, hand-picked mutation probes - plausible defects injected one at a time, in memory, to see whether the tests notice. Use when reviewing tests or a change, auditing test quality, or checking whether "all green" really means the behavior is verified. Not a full mutation-testing campaign.
---

# Mutation probing

A passing suite only proves that the tests pass. A mutation probe asks the sharper question:
*if this specific plausible bug existed, would any test fail?* A surviving probe is concrete,
reproducible evidence of a verification gap - usually more convincing than coverage numbers
or a reviewer's opinion.

This is a targeted audit technique, not exhaustive mutation testing. Use only enough probes to
investigate the component's highest-risk failure classes; no fixed count is required.

## Requires

The bundled harness needs Python 3.11+ and the project's Python environment with pytest. For
other languages or test runners, use the manual approach described at the end of section 2 -
that is the only sanctioned fallback; do not improvise a different harness.

## 1. Choose probes from risk, not from syntax

Read the contract (spec, docstrings, README) and the code under test, then ask: *which
realistic mistakes would a developer make here, and would they matter?* Good probe families:

- **State and history:** forget earlier entries (clear a cache/map after lookup), reuse the
  first resolved object for every later request, share a counter between instances.
  Single-entity test fixtures hide these.
- **Value preservation:** drop or reset fields while passing a record through a stage
  (keep only the classification, lose measurements/metadata/provenance), convert types
  silently (`-0.0` to `0.0`, `1.0` to `1`, tuple to list).
- **Boundaries:** shift a limit by one (`<` vs `<=`, `max` vs `max + 1`), accept the first
  value outside a range, skip validation for one input class.
- **Error handling:** swallow an exception, wrap it in another category, lose `__cause__`,
  catch `BaseException` and convert interrupts, re-raise a cleanup error instead of the
  original.
- **Ordering and identity:** reverse an iteration, include an excluded field in a key or
  hash, drop a field from a key, reorder positional outputs.
- **Counting and accounting:** reset or skip a counter increment, count per attempt instead of
  per entity, stop a loop early or late.

Skip probes that are equivalent (no observable behavior change) or only reachable through
impossible states. Note them as equivalent if you considered them.

## 2. Run the probes

For Python projects tested with pytest, use the bundled harness. It runs the unmutated
baseline first, then each mutant in its own fresh interpreter. An import hook hands the target
module mutated source **the first time it is imported** (normally while pytest collects the
tests), so the module executes once, under the project's normal import configuration
(`pythonpath`, conftest, editable installs), and every importer - including package
re-exports - sees the mutated objects. **No file is modified.**

```bash
# mutants.json: [{"id": "M1", "module": "pkg.runner", "old": "<exact fragment>",
#                 "new": "<replacement>", "description": "forget instance history"}]
uv run python <skill-dir>/scripts/probe.py --mutants mutants.json --json probes.json \
    -- tests/area -q -p no:cacheprovider
```

- Run it inside the project's environment (`uv run python`, the venv's `python`, ...), so the
  code under test and pytest import. Use `--python` to name another interpreter.
- `old` must occur exactly once in the module; widen the fragment until it is unique.
- Statuses: `KILLED` (tests failed or could not be collected because of the mutation - good),
  `SURVIVED` (gap), `NOT_EXERCISED` (the selected tests never imported the module in-process -
  wrong module name or test selection), `INVALID` (fragment not unique), `ERROR` (mutated
  source does not compile, unsupported loader, broken run), `TIMEOUT`. The JSON output keeps
  the last lines of each run, so you can check *why* a probe was killed.
- Exit status: 0 all killed, 1 some survived, 2 invalid input, failing baseline, or any
  `INVALID`/`ERROR`/`NOT_EXERCISED`/`TIMEOUT`. A failing baseline stops the run - deselect
  known failures with pytest arguments (`--deselect <node-id>`) and say so in the report.

**Limitations - check before calling a survivor a gap.** The mutation exists only in the
pytest process. Code executed elsewhere runs unmutated: subprocesses (e.g. CLI tests that start
the program), spawned or forked workers, external executables, and modules re-loaded from
source. If the tests that should catch a probe exercise the code that way, a `SURVIVED` result
proves nothing; use a scratch copy of the project with the mutation applied to the file
instead. Only modules loaded by Python's standard source loader can be probed; extension
modules, zip imports and modules loaded through custom import hooks are reported as `ERROR`.
pytest's assertion rewriting is handled (the target module itself is not rewritten).

For other languages or runners, apply the same idea by hand: mutate in a scratch copy or via
monkeypatching inside a test session, never in the working tree you are reviewing.

## 3. Report

For each surviving probe report:

1. The probe (module, fragment, replacement) and the plausible defect it represents.
2. Why it matters (which contract clause or downstream behavior it would break).
3. The smallest test change that would kill it - preferably strengthening or parametrizing an
   existing test rather than adding a new one.

Also list killed probes briefly (they document what *is* verified) and equivalent probes you
skipped. Treat the result as diagnostic evidence about the suite, not as a score: a killed
probe does not prove the test is good, and a survivor is not automatically a defect in the
production code.

When tests are added in response, re-run the same probes to confirm they are now killed.
