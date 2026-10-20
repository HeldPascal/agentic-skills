import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_baseline
import check_requirements
import compose_prompt
import run_checks

# --- compose_prompt -------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "brief.md").write_text("brief")
    (tmp_path / "docs" / "spec.md").write_text("spec")
    return tmp_path


def context(workspace: Path, **extra: object) -> dict:
    return {
        "work_package": "WP1",
        "agent": "claude",
        "task": "Write the authoritative tests for WP1.",
        "workspace": str(workspace),
        "spec": "docs/spec.md",
        "baseline": "abc123",
        "report": "/tmp/report.md",
        "ownership": ["tests/"],
        "isolation": ["../wp1-impl", "branch wp1-impl"],
        **extra,
    }


def test_prompt_points_at_skill_files_and_lists_context(workspace: Path) -> None:
    validated = compose_prompt.validate(
        "test-author",
        context(
            workspace,
            intent=["docs/brief.md"],
            overrides=[{"instruction": "Skip slow tests.", "reason": "CI limit"}],
        ),
    )

    prompt = compose_prompt.render("test-author", validated)

    assert "1. Load the skill `dev-workflow` with your Skill tool" in prompt
    assert "`roles/test-author.md` (your role; mode: initial)" in prompt
    assert "do not recreate it from memory" in prompt
    assert "Write the authoritative tests for WP1." in prompt
    assert "- Baseline commit: abc123" in prompt
    assert f"- Specification: {workspace.resolve() / 'docs' / 'spec.md'}" in prompt
    assert "  - ../wp1-impl" in prompt
    assert "1. Skip slow tests. (reason: CI limit)" in prompt


def test_prompt_states_absence_of_overrides(workspace: Path) -> None:
    prompt = compose_prompt.render(
        "test-author", compose_prompt.validate("test-author", context(workspace))
    )

    assert prompt.rstrip().endswith("None.")


def test_every_role_file_named_by_the_script_exists() -> None:
    for role in compose_prompt.ROLES:
        assert (compose_prompt.SKILL_DIR / "roles" / f"{role}.md").is_file()


def test_critic_may_start_before_the_draft_exists(workspace: Path) -> None:
    ctx = {
        "work_package": "WP1",
        "agent": "codex",
        "task": "Critique the WP1 draft.",
        "workspace": str(workspace),
        "spec": "docs/not-yet-written.md",
        "intent": ["docs/brief.md"],
    }

    validated = compose_prompt.validate("spec-critic", ctx)
    assert validated["mode"] == "initial"
    prompt = compose_prompt.render("spec-critic", validated)
    assert "1. Use the skill `$dev-workflow`" in prompt
    assert "2. Your role uses this skill: use the skill `$spec-critique`." in prompt
    delta = {**ctx, "mode": "delta-review", "change": "Add X.", "change_reason": "Gap."}
    with pytest.raises(compose_prompt.ContextError, match="not a file"):
        compose_prompt.validate("spec-critic", delta)


@pytest.mark.parametrize(
    ("role", "change", "message"),
    [
        pytest.param("test-author", {"baseline": None}, "lacks", id="missing"),
        pytest.param("test-author", {"spce": "x"}, "unknown context keys", id="typo"),
        pytest.param(
            "test-author",
            {"intent": ["docs/old-brief.md"]},
            "not a file",
            id="stale-reference",
        ),
        pytest.param(
            "test-author", {"intent": ["docs"]}, "not a file", id="directory-as-doc"
        ),
        pytest.param("test-author", {"isolation": []}, "isolation", id="no-isolation"),
        pytest.param(
            "implementer", {"ownership": None}, "ownership", id="no-ownership"
        ),
        pytest.param(
            "spec-critic", {"intent": []}, "intent", id="critic-without-intent"
        ),
        pytest.param(
            "spec-critic",
            {"intent": ["docs/brief.md"], "mode": "delta-review"},
            "change",
            id="delta-review-without-change",
        ),
        pytest.param("test-author", {"mode": "review"}, "mode", id="bad-mode"),
        pytest.param("spec-author", {}, "lacks", id="author-needs-intent"),
        pytest.param(
            "test-author",
            {"overrides": [{"instruction": "x"}]},
            "overrides",
            id="override-without-reason",
        ),
        pytest.param("tester", {}, "unknown role", id="unknown-role"),
        pytest.param("test-author", {"agent": "gemini"}, "agent", id="unknown-agent"),
    ],
)
def test_invalid_contexts_are_rejected(
    workspace: Path, role: str, change: dict, message: str
) -> None:
    ctx = {k: v for k, v in {**context(workspace), **change}.items() if v is not None}

    with pytest.raises(compose_prompt.ContextError, match=message):
        compose_prompt.validate(role, ctx)


def test_main_writes_prompt_file(workspace: Path, tmp_path: Path) -> None:
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text(json.dumps(context(workspace)))
    out = tmp_path / "prompts" / "wp1-test-author.md"

    code = compose_prompt.main(
        ["--role", "test-author", "--context", str(ctx_file), "--out", str(out)]
    )

    assert code == 0
    assert out.read_text().startswith("# Test Author - WP1")


# --- check_baseline -------------------------------------------------------


def sh(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    sh(repo, "add", name)
    sh(repo, "commit", "-q", "-m", name)
    return sh(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path, str]:
    """A clone whose local main is ahead of origin/main, plus a stale worktree."""
    origin = tmp_path / "origin"
    origin.mkdir()
    sh(origin, "init", "-q", "-b", "main")
    for key, value in {
        "user.name": "t",
        "user.email": "t@example.org",
        "commit.gpgsign": "false",
    }.items():
        sh(origin, "config", key, value)
    commit(origin, "a")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    for key, value in {
        "user.name": "t",
        "user.email": "t@example.org",
        "commit.gpgsign": "false",
    }.items():
        sh(clone, "config", key, value)
    newest = commit(clone, "b")
    stale = tmp_path / "stale"
    sh(clone, "worktree", "add", "-q", "-b", "feature", str(stale), "origin/main")
    return clone, stale, newest


def test_stale_worktree_base_is_reported(repos: tuple[Path, Path, str]) -> None:
    _, stale, _ = repos

    facts, problems = check_baseline.check(stale, base="main")

    assert problems == [
        (
            "HEAD lacks 1 commit(s) of local main - "
            "the worktree may be based on a stale ref"
        )
    ]
    assert "local main is 1 ahead / 0 behind origin/main" in facts


def test_matching_baseline_passes(repos: tuple[Path, Path, str]) -> None:
    clone, _, newest = repos

    facts, problems = check_baseline.check(clone, expect=newest, base="main")

    assert problems == []
    assert any("equals expected baseline" in fact for fact in facts)


def test_wrong_baseline_and_dirty_tree_are_reported(
    repos: tuple[Path, Path, str],
) -> None:
    clone, _, _ = repos
    (clone / "untracked.txt").write_text("x")

    _, problems = check_baseline.check(clone, expect="origin/main")

    assert len(problems) == 2
    assert problems[0] == "working tree has 1 uncommitted change(s)"
    assert "differs from expected baseline origin/main" in problems[1]


def test_untracked_files_count_even_when_hidden_by_git_config(
    repos: tuple[Path, Path, str],
) -> None:
    clone, _, newest = repos
    sh(clone, "config", "status.showUntrackedFiles", "no")
    (clone / "untracked.txt").write_text("x")

    _, problems = check_baseline.check(clone, expect=newest)

    assert problems == ["working tree has 1 uncommitted change(s)"]


def test_unknown_ref_is_an_input_error(repos: tuple[Path, Path, str]) -> None:
    clone, _, _ = repos

    assert check_baseline.main(["--worktree", str(clone), "--expect", "nope"]) == 2


# --- run_checks -----------------------------------------------------------


def test_all_stage_commands_run_and_failures_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "checks.json"
    config.write_text(
        json.dumps(
            {
                "fast": [
                    {"name": "fails", "cmd": "echo broken; exit 3"},
                    {"name": "passes", "cmd": "echo fine"},
                ],
                "full": [{"name": "later", "cmd": "echo full"}],
            }
        )
    )
    logs = tmp_path / "logs"

    code = run_checks.main(
        [
            "--config",
            str(config),
            "--stage",
            "fast",
            "--stage",
            "full",
            "--cwd",
            str(tmp_path),
            "--log-dir",
            str(logs),
        ]
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL(3)   fast/fails" in out and out.count("broken") == 1
    assert "PASS      fast/passes" in out
    assert "PASS      full/later" in out
    (invocation,) = logs.iterdir()
    assert (invocation / "01-fast-fails.log").read_text() == (
        "$ echo broken; exit 3\nbroken\n"
    )
    assert sorted(p.name for p in invocation.iterdir()) == [
        "01-fast-fails.log",
        "02-fast-passes.log",
        "03-full-later.log",
    ]


@pytest.mark.parametrize(
    "content",
    [
        pytest.param({"fast": []}, id="empty-stage"),
        pytest.param({"fast": [{"name": "x"}]}, id="missing-cmd"),
        pytest.param({"slow": [{"name": "x", "cmd": "true"}]}, id="unknown-stage"),
        pytest.param(
            {"fast": [{"name": "x", "cmd": "true"}, {"name": "x", "cmd": "false"}]},
            id="duplicate-name",
        ),
    ],
)
def test_invalid_check_configs_are_rejected(tmp_path: Path, content: dict) -> None:
    config = tmp_path / "checks.json"
    config.write_text(json.dumps(content))

    with pytest.raises(ValueError):
        run_checks.load_checks(config, ["fast"])


def test_other_harnesses_get_skill_file_paths(workspace: Path) -> None:
    validated = compose_prompt.validate(
        "reviewer-tests",
        {
            "work_package": "WP1",
            "agent": "other",
            "task": "Review the WP1 tests.",
            "workspace": str(workspace),
            "spec": "docs/spec.md",
            "diff": "base..head",
            "report": "review.md",
        },
    )

    prompt = compose_prompt.render("reviewer-tests", validated)

    skills = compose_prompt.SKILL_DIR.parent
    assert f"1. Read {skills / 'dev-workflow' / 'SKILL.md'}" in prompt
    assert f"read {skills / 'mutation-probing' / 'SKILL.md'}" in prompt


# --- check_requirements ---------------------------------------------------


def make_skill(directory: Path, name: str, declared: str | None = None) -> None:
    (directory / name).mkdir(parents=True)
    (directory / name / "SKILL.md").write_text(
        f"---\nname: {declared or name}\ndescription: x\n---\n"
    )


def test_missing_and_misnamed_skills_are_reported_per_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    shared = tmp_path / "home" / ".agents" / "skills"
    for name in ("dev-workflow", "requirements-discovery", "spec-critique"):
        make_skill(shared, name)
    make_skill(shared, "mutation-probing", declared="something-else")
    claude_dir = tmp_path / "home" / ".claude" / "skills"
    for name in check_requirements.WORKFLOW_SKILLS:
        make_skill(claude_dir, name)
    project = tmp_path / "project"

    facts, problems = check_requirements.check(
        ["claude", "codex"], project, orca=False, extra_dirs={}
    )

    codex_dirs = ", ".join(
        str(d) for d in check_requirements.skill_dirs("codex", project)
    )
    assert [p for p in problems if p.startswith(("claude", "codex"))] == [
        f"codex: skill mutation-probing not found in {codex_dirs}"
    ]
    assert any(f.startswith("claude: skill dev-workflow at") for f in facts)


def test_unknown_harness_needs_an_explicit_directory(tmp_path: Path) -> None:
    extra = tmp_path / "skills"
    for name in check_requirements.WORKFLOW_SKILLS:
        make_skill(extra, name)

    _, without = check_requirements.check(["pi"], tmp_path, False, {})
    _, with_dir = check_requirements.check(["pi"], tmp_path, False, {"pi": [extra]})

    assert any("unknown harness" in p for p in without)
    assert not [p for p in with_dir if p.startswith("pi")]
