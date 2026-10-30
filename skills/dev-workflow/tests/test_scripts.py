import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_baseline
import check_requirements
import compose_prompt
import run_checks
import snapshot_spec

# --- compose_prompt -------------------------------------------------------


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    sh(path, "init", "-q", "-b", "main")
    for key, value in {
        "user.name": "t",
        "user.email": "t@example.org",
        "commit.gpgsign": "false",
    }.items():
        sh(path, "config", key, value)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A git worktree root with committed documents (HEAD is the baseline)."""
    root = tmp_path / "ws"
    init_repo(root)
    (root / "docs").mkdir()
    (root / "docs" / "brief.md").write_text("brief")
    (root / "docs" / "spec.md").write_text("spec")
    sh(root, "add", ".")
    sh(root, "commit", "-q", "-m", "baseline")
    return root


def context(workspace: Path, **extra: object) -> dict:
    return {
        "work_package": "WP1",
        "agent": "claude",
        "task": "Write the authoritative tests for WP1.",
        "workspace": str(workspace),
        "spec": "docs/spec.md",
        "baseline": sh(workspace, "rev-parse", "HEAD"),
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
    assert f"- Baseline commit: {sh(workspace, 'rev-parse', 'HEAD')}" in prompt
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
    delta = {
        **ctx,
        "mode": "delta-review",
        "change": "Add X.",
        "change_reason": "Gap.",
        "snapshot": "docs/spec.md",
    }
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


def test_main_reports_the_workspace_to_dispatch_into(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text(json.dumps(context(workspace)))
    out = tmp_path / "prompt.md"

    compose_prompt.main(
        ["--role", "test-author", "--context", str(ctx_file), "--out", str(out)]
    )

    assert json.loads(capsys.readouterr().out) == {
        "prompt": str(out.resolve()),
        "workspace": str(workspace.resolve()),
        "role": "test-author",
        "mode": "initial",
    }


def test_workspace_must_sit_exactly_on_the_baseline(workspace: Path) -> None:
    old = sh(workspace, "rev-parse", "HEAD")
    commit(workspace, "later.txt")

    with pytest.raises(compose_prompt.ContextError, match="does not match baseline"):
        compose_prompt.validate("test-author", context(workspace, baseline=old))


def test_workspace_must_be_the_worktree_root(workspace: Path) -> None:
    ctx = {
        **context(workspace),
        "workspace": str(workspace / "docs"),
        "spec": "spec.md",
    }

    with pytest.raises(compose_prompt.ContextError, match="not the root"):
        compose_prompt.validate("test-author", ctx)


def test_set_overrides_fields_and_revalidates(workspace: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    init_repo(other)
    commit(other, "x.txt")
    base = context(workspace)
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text(json.dumps(base))
    out = tmp_path / "repair.md"

    code = compose_prompt.main(
        [
            "--role",
            "test-author",
            "--context",
            str(ctx_file),
            "--set",
            "mode=repair",
            "--set",
            'ownership=["tests/", "fixtures/"]',
            "--out",
            str(out),
        ]
    )
    prompt = out.read_text()
    moved = compose_prompt.main(
        [
            "--role",
            "test-author",
            "--context",
            str(ctx_file),
            "--set",
            f"workspace={other}",
            "--out",
            str(tmp_path / "moved.md"),
        ]
    )

    assert code == 0
    assert "(dev-workflow, mode: repair)" in prompt
    assert "  - fixtures/" in prompt
    assert moved == 2  # the old baseline does not exist in the other worktree


@pytest.mark.parametrize(
    "assignment",
    ["spce=x", "noequals", "ownership=tests/"],
    ids=["unknown-key", "no-value", "list-not-json"],
)
def test_invalid_set_assignments_are_rejected(workspace: Path, assignment: str) -> None:
    with pytest.raises(compose_prompt.ContextError):
        compose_prompt.apply_sets(context(workspace), [assignment])


def test_describe_lists_required_and_optional_fields() -> None:
    text = compose_prompt.describe("reviewer-code")
    required = text.split("required:")[1].split("optional:")[0]
    optional = text.split("optional:")[1]

    for key in ("task", "workspace", "agent", "spec", "diff", "report"):
        assert f"  {key} " in required
    assert "  baseline " in optional
    assert "isolation" in compose_prompt.describe("implementer").split("optional:")[0]
    assert (
        "isolation"
        not in compose_prompt.describe("implementer", "repair").split("optional:")[0]
    )


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


def write_checks(tmp_path: Path, checks: dict) -> Path:
    config = tmp_path / "checks.json"
    config.write_text(json.dumps(checks))
    return config


def test_timeouts_stop_the_command_and_its_children(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pid_file = tmp_path / "child.pid"
    config = write_checks(
        tmp_path,
        {
            "fast": [
                # The background child must not outlive the timed-out check.
                {
                    "name": "hangs",
                    "cmd": f"sleep 60 & echo $! > {pid_file}; sleep 60",
                    "timeout": 1,
                },
                {"name": "quick", "cmd": "echo done"},
            ]
        },
    )
    started = time.monotonic()

    code = run_checks.main(
        ["--config", str(config), "--stage", "fast", "--cwd", str(tmp_path)]
    )

    out = capsys.readouterr().out
    assert time.monotonic() - started < 15
    assert code == 1
    assert "TIMEOUT   fast/hangs" in out
    assert "PASS      fast/quick" in out
    assert process_stopped(pid_file)


def test_default_timeout_applies_only_to_checks_without_their_own(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_checks(
        tmp_path,
        {
            "fast": [
                {"name": "own-limit", "cmd": "sleep 2", "timeout": 10},
                {"name": "default-limit", "cmd": "sleep 2"},
            ]
        },
    )

    code = run_checks.main(
        [
            "--config",
            str(config),
            "--stage",
            "fast",
            "--cwd",
            str(tmp_path),
            "--timeout",
            "1",
        ]
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "PASS      fast/own-limit" in out
    assert "TIMEOUT   fast/default-limit" in out


@pytest.mark.parametrize("timeout", [0, -1, True, "5"])
def test_invalid_timeouts_are_rejected(tmp_path: Path, timeout: object) -> None:
    config = write_checks(
        tmp_path, {"fast": [{"name": "x", "cmd": "true", "timeout": timeout}]}
    )

    with pytest.raises(ValueError, match="timeout"):
        run_checks.load_checks(config, ["fast"])


# --- snapshot_spec --------------------------------------------------------


def write_spec(path: Path, version: str, body: str = "body") -> Path:
    path.write_text(f'---\nversion: "{version}"\nstatus: accepted\n---\n\n{body}\n')
    return path


def test_snapshot_is_a_read_only_copy_named_by_version(tmp_path: Path) -> None:
    spec = write_spec(tmp_path / "wp1.md", "0.1.2")

    target = snapshot_spec.snapshot(spec)

    assert target == tmp_path / "wp1.v0.1.2.md"
    assert target.read_text() == spec.read_text()
    assert not os.access(target, os.W_OK)


def test_snapshots_survive_later_edits_and_are_idempotent(tmp_path: Path) -> None:
    spec = write_spec(tmp_path / "wp1.md", "0.1.2", "accepted text")
    first = snapshot_spec.snapshot(spec)
    assert snapshot_spec.snapshot(spec) == first

    write_spec(spec, "0.1.3", "patched text")
    second = snapshot_spec.snapshot(spec)

    assert first.read_text().endswith("accepted text\n")
    assert second == tmp_path / "wp1.v0.1.3.md"
    assert second.read_text().endswith("patched text\n")


def test_changed_content_under_an_existing_version_is_refused(tmp_path: Path) -> None:
    spec = write_spec(tmp_path / "wp1.md", "0.1.2", "accepted text")
    snapshot = snapshot_spec.snapshot(spec)
    write_spec(spec, "0.1.2", "silently edited")

    assert snapshot_spec.main([str(spec)]) == 1
    assert snapshot.read_text().endswith("accepted text\n")


@pytest.mark.parametrize(
    "content", ["no front matter\n", "---\nstatus: draft\n---\nbody\n"]
)
def test_specs_without_a_version_are_rejected(tmp_path: Path, content: str) -> None:
    spec = tmp_path / "wp1.md"
    spec.write_text(content)

    assert snapshot_spec.main([str(spec)]) == 2
    assert list(tmp_path.iterdir()) == [spec]


def process_stopped(pid_file: Path, within: float = 5.0) -> bool:
    """Wait until the process whose PID is in pid_file no longer exists."""
    deadline = time.monotonic() + within
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    pid = int(pid_file.read_text())
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    os.kill(pid, 9)  # do not leak the process if the assertion fails
    return False


def test_describe_accepts_the_role_as_its_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert compose_prompt.main(["--describe", "reviewer-code"]) == 0
    by_value = capsys.readouterr().out
    assert compose_prompt.main(["--describe", "--role", "reviewer-code"]) == 0

    assert by_value == capsys.readouterr().out
    assert "  diff " in by_value


def test_mode_is_rejected_when_rendering(workspace: Path, tmp_path: Path) -> None:
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text(json.dumps(context(workspace)))
    out = tmp_path / "prompt.md"

    code = compose_prompt.main(
        [
            "--role",
            "implementer",
            "--context",
            str(ctx_file),
            "--mode",
            "repair",
            "--out",
            str(out),
        ]
    )

    assert code == 2
    assert not out.exists()


def revision_context(workspace: Path, snapshot: Path, **extra: object) -> dict:
    return {
        "work_package": "WP1",
        "agent": "codex",
        "task": "Apply the classified change to the specification.",
        "workspace": str(workspace),
        "mode": "revision",
        "spec": "docs/spec.md",
        "snapshot": str(snapshot),
        "intent": ["docs/brief.md"],
        "change": "Add a timeout field.",
        "change_reason": "Review found no timeout contract.",
        **extra,
    }


@pytest.fixture
def accepted(workspace: Path, tmp_path: Path) -> Path:
    """A read-only snapshot of the accepted spec in a run directory."""
    working = tmp_path / "run" / "specs" / "spec.md"
    working.parent.mkdir(parents=True)
    working.write_text('---\nversion: "0.1.0"\nstatus: accepted\n---\n\nbody\n')
    return snapshot_spec.snapshot(working)


def test_revision_edits_the_working_file_and_reads_the_snapshot(
    workspace: Path, accepted: Path
) -> None:
    validated = compose_prompt.validate(
        "spec-author", revision_context(workspace, accepted)
    )

    prompt = compose_prompt.render("spec-author", validated)

    working = workspace.resolve() / "docs" / "spec.md"
    assert f"- Working specification (edit this file): {working}" in prompt
    assert (
        f"- Accepted snapshot (read-only reference, never edit): {accepted.resolve()}"
        in prompt
    )


def test_revision_without_a_snapshot_is_rejected(
    workspace: Path, accepted: Path
) -> None:
    ctx = revision_context(workspace, accepted)
    del ctx["snapshot"]

    with pytest.raises(compose_prompt.ContextError, match="snapshot"):
        compose_prompt.validate("spec-author", ctx)


def test_a_snapshot_is_never_handed_out_for_editing(
    workspace: Path, accepted: Path
) -> None:
    as_spec = revision_context(workspace, accepted, spec=str(accepted))
    read_only = workspace / "docs" / "frozen.md"
    read_only.write_text("frozen")
    read_only.chmod(0o444)
    not_writable = revision_context(workspace, accepted, spec="docs/frozen.md")

    with pytest.raises(compose_prompt.ContextError, match="not the snapshot"):
        compose_prompt.validate("spec-author", as_spec)
    with pytest.raises(compose_prompt.ContextError, match="not writable"):
        compose_prompt.validate("spec-author", not_writable)


def test_delta_review_needs_the_snapshot_it_started_from(
    workspace: Path, accepted: Path
) -> None:
    ctx = revision_context(workspace, accepted, agent="claude", mode="delta-review")

    validated = compose_prompt.validate("spec-critic", ctx)
    del ctx["snapshot"]

    assert validated["snapshot"] == str(accepted.resolve())
    with pytest.raises(compose_prompt.ContextError, match="snapshot"):
        compose_prompt.validate("spec-critic", ctx)
