import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import probe


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny package with a module under test and one passing test file."""
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef unused(x):\n    return x\n"
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    return tmp_path


def write_mutants(path: Path, mutants: list[dict[str, str]]) -> Path:
    target = path / "mutants.json"
    target.write_text(json.dumps(mutants))
    return target


def run(project: Path, mutants: list[dict[str, str]]) -> tuple[int, dict]:
    mutants_file = write_mutants(project, mutants)
    result_file = project / "result.json"
    code = probe.main(
        [
            "--mutants",
            str(mutants_file),
            "--json",
            str(result_file),
            "--",
            "-q",
            "-p",
            "no:cacheprovider",
            "test_calc.py",
        ]
    )
    return code, json.loads(result_file.read_text())


def statuses(result: dict) -> dict[str, str]:
    return {entry["id"]: entry["status"] for entry in result["mutants"]}


def test_detected_and_undetected_mutants_are_reported_separately(
    project: Path,
) -> None:
    code, result = run(
        project,
        [
            {"id": "sub", "module": "calc", "old": "a + b", "new": "a - b"},
            {"id": "dead", "module": "calc", "old": "return x", "new": "return 0"},
        ],
    )

    assert result["baseline"]["status"] == "PASSED"
    assert statuses(result) == {"sub": "KILLED", "dead": "SURVIVED"}
    assert code == 1


def test_all_killed_exits_zero_and_leaves_source_untouched(
    project: Path,
) -> None:
    before = (project / "calc.py").read_text()

    code, result = run(
        project,
        [{"id": "sub", "module": "calc", "old": "a + b", "new": "a * b"}],
    )

    assert statuses(result) == {"sub": "KILLED"}
    assert code == 0
    assert (project / "calc.py").read_text() == before


@pytest.mark.parametrize(
    ("mutant", "expected"),
    [
        pytest.param(
            {"id": "m", "module": "calc", "old": "return", "new": "yield"},
            "INVALID",
            id="ambiguous-old-fragment",
        ),
        pytest.param(
            {"id": "m", "module": "calc", "old": "a + b", "new": "a +"},
            "ERROR",
            id="syntax-error",
        ),
        pytest.param(
            {"id": "m", "module": "nope", "old": "a", "new": "b"},
            "NOT_EXERCISED",
            id="module-never-imported",
        ),
    ],
)
def test_broken_mutants_are_not_counted_as_killed(
    project: Path, mutant: dict[str, str], expected: str
) -> None:
    code, result = run(project, [mutant])

    assert statuses(result) == {"m": expected}
    assert code == 2


def test_failing_baseline_stops_before_any_mutant(project: Path) -> None:
    (project / "test_calc.py").write_text("def test_fails():\n    assert False\n")

    code, result = run(
        project,
        [{"id": "sub", "module": "calc", "old": "a + b", "new": "a - b"}],
    )

    assert result["baseline"]["status"] == "FAILED"
    assert result["mutants"] == []
    assert code == 2


@pytest.mark.parametrize(
    "content",
    [
        pytest.param([], id="empty"),
        pytest.param([{"id": "x", "module": "calc", "old": "a"}], id="missing-key"),
        pytest.param(
            [{"id": "x", "module": "calc", "old": "a", "new": "a"}], id="no-op"
        ),
        pytest.param(
            [
                {"id": "x", "module": "calc", "old": "a", "new": "b"},
                {"id": "x", "module": "calc", "old": "b", "new": "c"},
            ],
            id="duplicate-id",
        ),
    ],
)
def test_invalid_mutant_files_are_rejected(tmp_path: Path, content: list) -> None:
    path = tmp_path / "mutants.json"
    path.write_text(json.dumps(content))

    with pytest.raises(ValueError):
        probe.load_mutants(path)


def test_timeout_is_reported(project: Path) -> None:
    (project / "test_calc.py").write_text(
        "import time\nfrom calc import add\n\n\n"
        "def test_add():\n    time.sleep(0 if add(1, 1) == 2 else 30)\n"
    )
    mutants_file = write_mutants(
        project, [{"id": "slow", "module": "calc", "old": "a + b", "new": "a * b"}]
    )

    baseline, outcomes = probe.run_probes(
        probe.load_mutants(mutants_file),
        ["-q", "-p", "no:cacheprovider", "test_calc.py"],
        timeout=5,
    )

    assert baseline.status == "PASSED"
    assert [outcome.status for outcome in outcomes] == ["TIMEOUT"]


def probe_layout(
    root: Path, files: dict[str, str], mutant: dict[str, str], *args: str
) -> str:
    """Write a scratch project, run one mutant against it, return its status."""
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)
    mutants = write_mutants(root, [mutant])
    baseline, outcomes = probe.run_probes(
        probe.load_mutants(mutants), ["-q", "-p", "no:cacheprovider", *args]
    )
    assert baseline.status == "PASSED", baseline.output_tail
    return outcomes[0].status


def test_deleting_a_used_function_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    status = probe_layout(
        tmp_path,
        {
            "calc.py": "def add(a, b):\n    return a + b\n",
            "test_calc.py": "from calc import add\n\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n",
        },
        {
            "id": "m",
            "module": "calc",
            "old": "def add(a, b):\n    return a + b\n",
            "new": "\n",
        },
    )

    assert status == "KILLED"


def test_mutation_reaches_names_reexported_by_a_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    status = probe_layout(
        tmp_path,
        {
            "pkg/__init__.py": "from .calc import add\n",
            "pkg/calc.py": "def add(a, b):\n    return a + b\n",
            "test_pkg.py": "from pkg import add\n\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n",
        },
        {"id": "m", "module": "pkg.calc", "old": "a + b", "new": "a - b"},
    )

    assert status == "KILLED"


def test_module_side_effects_run_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    status = probe_layout(
        tmp_path,
        {
            "registry.py": "ENTRIES = []\n",
            "plugin.py": "import registry\n\nregistry.ENTRIES.append('plugin')\n"
            "\n\ndef unused():\n    return 1\n",
            "test_plugin.py": "import plugin\nimport registry\n\n\n"
            "def test_registered_once():\n"
            "    assert registry.ENTRIES == ['plugin']\n",
        },
        {"id": "m", "module": "plugin", "old": "return 1", "new": "return 2"},
    )

    assert status == "SURVIVED"


def test_project_import_configuration_applies_to_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    status = probe_layout(
        tmp_path,
        {
            "pytest.ini": "[pytest]\npythonpath = src\n",
            "src/calc.py": "def add(a, b):\n    return a + b\n",
            "tests/test_calc.py": "from calc import add\n\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n",
        },
        {"id": "m", "module": "calc", "old": "a + b", "new": "a - b"},
        "tests",
    )

    assert status == "KILLED"


def test_tests_that_never_import_the_target_are_reported(
    project: Path,
) -> None:
    (project / "other.py").write_text("def f():\n    return 1\n")

    code, result = run(
        project,
        [{"id": "m", "module": "other", "old": "return 1", "new": "return 2"}],
    )

    assert statuses(result) == {"m": "NOT_EXERCISED"}
    assert code == 2


def test_killed_probes_keep_the_failing_output(project: Path) -> None:
    _, result = run(
        project,
        [{"id": "sub", "module": "calc", "old": "a + b", "new": "a - b"}],
    )

    tail = "\n".join(result["mutants"][0]["output_tail"])
    assert "assert -1 == 5" in tail


def test_modules_registered_for_assertion_rewriting_are_mutated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    status = probe_layout(
        tmp_path,
        {
            "conftest.py": "import pytest\n\npytest.register_assert_rewrite('calc')\n",
            "calc.py": "def add(a, b):\n    return a + b\n",
            "test_calc.py": "from calc import add\n\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n",
        },
        {"id": "m", "module": "calc", "old": "a + b", "new": "a - b"},
    )

    assert status == "KILLED"


def test_source_encoding_declarations_are_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    source = "# -*- coding: latin-1 -*-\n# Grüße\ndef add(a, b):\n    return a + b\n"
    (tmp_path / "calc.py").write_bytes(source.encode("latin-1"))
    status = probe_layout(
        tmp_path,
        {
            "test_calc.py": "from calc import add\n\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n",
        },
        {"id": "m", "module": "calc", "old": "a + b", "new": "a - b"},
    )

    assert status == "KILLED"


CUSTOM_LOADER_CONFTEST = """\
import importlib.machinery
import sys


class Loader(importlib.machinery.SourceFileLoader):
    def exec_module(self, module):
        module.loader_value = 42
        super().exec_module(module)


class Finder:
    def find_spec(self, name, path, target=None):
        if name != "calc":
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        spec.loader = Loader(spec.loader.name, spec.loader.path)
        return spec


sys.meta_path.insert(1, Finder())
"""


def test_custom_source_loaders_are_reported_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    status = probe_layout(
        tmp_path,
        {
            "conftest.py": CUSTOM_LOADER_CONFTEST,
            "calc.py": "def add(a, b):\n    return a + b\n\n\ndef unused():\n    return 1\n",
            "test_calc.py": "import calc\n\n\n"
            "def test_loader_ran():\n    assert calc.loader_value == 42\n",
        },
        {"id": "m", "module": "calc", "old": "return 1", "new": "return 2"},
    )

    assert status == "ERROR"
