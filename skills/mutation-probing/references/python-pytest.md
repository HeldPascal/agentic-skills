# In-process probes for Python and pytest

`scripts/probe_pytest.py` is a faster alternative to `probe_files.py` for Python projects tested
with pytest. It needs no checkout per run and probes uncommitted code.

## How it works

The script runs the unmutated baseline first, then each mutant in its own fresh interpreter. An
import hook hands the target **module** mutated source the first time it is imported (normally
while pytest collects the tests), so the module executes once, under the project's normal import
configuration (`pythonpath`, conftest, editable installs), and every importer - including package
re-exports - sees the mutated objects. No file is modified.

```bash
# mutants.json: [{"id": "M1", "module": "pkg.runner", "old": "<exact fragment>",
#                 "new": "<replacement>", "description": "forget instance history"}]
uv run python <skill-dir>/scripts/probe_pytest.py --mutants mutants.json --json probes.json \
    -- tests/area -q -p no:cacheprovider
```

- Run it inside the project's environment (`uv run python`, the virtualenv's `python`, ...) so
  the code under test and pytest import; `--python` names another interpreter.
- Mutants name a dotted `module` instead of a file; `old` must occur exactly once in it.
- Statuses: `KILLED` (tests failed), `FAILED` (tests could not be collected because of the
  mutation - a broken import, not necessarily a detecting test; judge from the output tail),
  `SURVIVED`, `NOT_EXERCISED` (the selected tests never imported the module in-process - wrong
  module name or test selection), `INVALID` (fragment not unique), `ERROR` (mutated source does
  not compile, unsupported loader, broken run), `TIMEOUT`. The JSON output keeps the last lines
  of each run so you can check *why* a probe was killed.
- Exit status: 0 all killed, 1 some survived, 2 invalid input, failing baseline, or any
  `INVALID`/`ERROR`/`NOT_EXERCISED`/`TIMEOUT`, 3 nothing survived but `FAILED` results need
  judgment. A failing baseline stops the run - deselect known
  failures with `--deselect <node-id>` and say so in the report.

## Limitations - choose `probe_files.py` instead when they apply

- The mutation exists only in the pytest process. Code executed elsewhere runs unmutated:
  subprocesses (e.g. CLI tests that start the program), spawned or forked workers, external
  executables, modules re-loaded from source. If the tests that should catch a probe exercise
  the code that way, a `SURVIVED` result proves nothing.
- Only modules loaded by Python's standard source loader can be probed; extension modules, zip
  imports and modules loaded through custom import hooks are reported as `ERROR`.
- pytest's assertion rewriting is handled (the target module itself is not rewritten).
