import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import probe_files

# A language-neutral "project": a shell function and a shell test script.
ADD = "add() { echo $(($1 + $2)); }\nunused() { echo 1; }\n"
TEST = '. ./add.sh\n[ "$(add 2 3)" = 5 ] || { echo "add failed"; exit 1; }\n'


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    for key, value in {
        "user.name": "t",
        "user.email": "t@example.org",
        "commit.gpgsign": "false",
    }.items():
        git(root, "config", key, value)
    (root / "add.sh").write_text(ADD)
    (root / "test.sh").write_text(TEST)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    return root


def run(repo: Path, mutants: list[dict[str, str]], tmp_path: Path) -> tuple[int, dict]:
    mutants_file = tmp_path / "mutants.json"
    mutants_file.write_text(json.dumps(mutants))
    result = tmp_path / "result.json"
    code = probe_files.main(
        [
            "--mutants",
            str(mutants_file),
            "--repo",
            str(repo),
            "--json",
            str(result),
            "--",
            "sh",
            "test.sh",
        ]
    )
    return code, json.loads(result.read_text())


def statuses(result: dict) -> dict[str, str]:
    return {entry["id"]: entry["status"] for entry in result["mutants"]}


def test_killed_and_surviving_probes_in_any_language(
    repo: Path, tmp_path: Path
) -> None:
    code, result = run(
        repo,
        [
            {"id": "sub", "file": "add.sh", "old": "$1 + $2", "new": "$1 - $2"},
            {"id": "dead", "file": "add.sh", "old": "echo 1", "new": "echo 2"},
        ],
        tmp_path,
    )

    assert result["baseline"]["status"] == "PASSED"
    assert statuses(result) == {"sub": "KILLED", "dead": "SURVIVED"}
    assert "add failed" in result["mutants"][0]["output_tail"]
    assert code == 1


def test_working_tree_and_worktree_list_are_left_untouched(
    repo: Path, tmp_path: Path
) -> None:
    (repo / "notes.txt").write_text("uncommitted")

    run(
        repo,
        [{"id": "sub", "file": "add.sh", "old": "$1 + $2", "new": "$1 - $2"}],
        tmp_path,
    )

    assert (repo / "add.sh").read_text() == ADD
    assert (repo / "notes.txt").read_text() == "uncommitted"
    worktrees = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert len(worktrees.splitlines()) == 1


def test_each_probe_starts_from_the_unmutated_file(repo: Path, tmp_path: Path) -> None:
    _, result = run(
        repo,
        [
            {"id": "first", "file": "add.sh", "old": "$1 + $2", "new": "$1 * $2"},
            {"id": "second", "file": "add.sh", "old": "echo 1", "new": "echo 2"},
        ],
        tmp_path,
    )

    assert statuses(result) == {"first": "KILLED", "second": "SURVIVED"}


@pytest.mark.parametrize(
    ("mutant", "detail"),
    [
        pytest.param(
            {"id": "m", "file": "add.sh", "old": "echo", "new": "printf"},
            "occurs 2 times",
            id="ambiguous",
        ),
        pytest.param(
            {"id": "m", "file": "missing.sh", "old": "a", "new": "b"},
            "file not found",
            id="missing-file",
        ),
    ],
)
def test_invalid_probes_are_reported(
    repo: Path, tmp_path: Path, mutant: dict[str, str], detail: str
) -> None:
    code, result = run(repo, [mutant], tmp_path)

    assert statuses(result) == {"m": "INVALID"}
    assert detail in result["mutants"][0]["detail"]
    assert code == 2


def test_failing_baseline_stops_before_any_probe(repo: Path, tmp_path: Path) -> None:
    (repo / "test.sh").write_text("exit 1\n")
    git(repo, "commit", "-qam", "break")

    code, result = run(
        repo,
        [{"id": "sub", "file": "add.sh", "old": "$1 + $2", "new": "$1 - $2"}],
        tmp_path,
    )

    assert result["baseline"]["status"] == "FAILED"
    assert result["mutants"] == []
    assert code == 2


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(
            {"id": "x", "file": "/etc/passwd", "old": "a", "new": "b"}, id="absolute"
        ),
        pytest.param(
            {"id": "x", "file": "../x", "old": "a", "new": "b"}, id="escaping"
        ),
        pytest.param(
            {"id": "x", "module": "m", "old": "a", "new": "b"}, id="wrong-key"
        ),
    ],
)
def test_invalid_mutant_files_are_rejected(tmp_path: Path, entry: dict) -> None:
    path = tmp_path / "mutants.json"
    path.write_text(json.dumps([entry]))

    with pytest.raises(ValueError):
        probe_files.load_mutants(path)
