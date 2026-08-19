from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "state.py"
TASK_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "task.py"


def run_state(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_task(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    return subprocess.run(
        [sys.executable, str(TASK_SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def start_and_finish_task(tmp_path: Path, task_id: str, *, termination_reason: str | None = None) -> None:
    assert run_task(tmp_path, "start", task_id).returncode == 0
    finish_args = ["finish", task_id]
    if termination_reason is not None:
        finish_args += ["--termination-reason", termination_reason]
    assert run_task(tmp_path, *finish_args).returncode == 0


def test_init_creates_expected_files(tmp_path: Path) -> None:
    result = run_state(tmp_path, "init")
    assert result.returncode == 0, result.stderr

    config = tmp_path / "config" / "orca-orchestrator" / "config.json"
    registry = tmp_path / "state" / "orca-orchestrator" / "registry.json"
    capabilities = tmp_path / "state" / "orca-orchestrator" / "capabilities.json"
    aggregates = tmp_path / "state" / "orca-orchestrator" / "aggregates.json"
    observations = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"
    archive = tmp_path / "state" / "orca-orchestrator" / "archive"

    assert config.exists()
    assert registry.exists()
    assert capabilities.exists()
    assert aggregates.exists()
    assert observations.exists()
    assert archive.is_dir()

    config_value = json.loads(config.read_text())
    assert config_value["schema_version"] == 1
    assert config_value["limits"]["max_rework_rounds"] == 2
    assert config_value["limits"]["max_spec_revisions"] == 1
    assert config_value["limits"]["max_dispatches"] == 8
    assert config_value["compaction"]["max_active_observations_per_combination"] == 50
    registry_value = json.loads(registry.read_text())
    assert registry_value["schema_version"] == 1
    assert registry_value["role_combinations"] == {}
    assert json.loads(capabilities.read_text())["schema_version"] == 1
    assert json.loads(aggregates.read_text())["schema_version"] == 1


def test_init_preserves_explicit_config_and_adds_new_defaults(tmp_path: Path) -> None:
    config = tmp_path / "config" / "orca-orchestrator" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"schema_version": 1, "exploration": {"enabled": False}}))

    result = run_state(tmp_path, "init")
    assert result.returncode == 0, result.stderr

    value = json.loads(config.read_text())
    assert value["exploration"]["enabled"] is False
    assert value["limits"]["max_rework_rounds"] == 2
    assert value["compaction"]["stale_after_days"] == 90


def test_observe_execution_updates_combination_and_role_combination_aggregates(
    tmp_path: Path,
) -> None:
    assert run_state(tmp_path, "init").returncode == 0

    observation = json.dumps(
        {
            "kind": "execution",
            "task_id": "task-1",
            "role": "developer",
            "task_type": "implementation",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
            "backend": "lmstudio",
            "completed": True,
        }
    )
    result = run_state(tmp_path, "observe", observation)
    assert result.returncode == 0, result.stderr

    path = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["schema_version"] == 1
    assert rows[0]["timestamp"].endswith("Z")
    assert rows[0]["harness"] == "pi"

    aggregates = json.loads(
        (tmp_path / "state" / "orca-orchestrator" / "aggregates.json").read_text()
    )
    combo = aggregates["combinations"]["pi|qwen/qwen3-coder-next|lmstudio|none|none"]
    assert combo["observations"] == 1
    assert combo["completed"] == 1
    assert combo["completion_rate"] == 1.0

    role_combo = aggregates["role_combinations"][
        "developer|pi|qwen/qwen3-coder-next|lmstudio|none|none"
    ]
    assert role_combo["observations"] == 1
    assert aggregates["tasks"] == {}


def test_observe_rejects_missing_kind(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    result = run_state(tmp_path, "observe", '{"task_type":"implementation"}')
    assert result.returncode == 1
    assert "kind" in result.stderr


def test_observe_execution_rejects_missing_required_fields(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    result = run_state(
        tmp_path, "observe", '{"kind":"execution","task_id":"t1","harness":"pi"}'
    )
    assert result.returncode == 1
    assert "missing required field" in result.stderr
    assert "role" in result.stderr
    assert "model" in result.stderr


def test_observe_execution_rejects_task_only_fields(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    observation = json.dumps(
        {
            "kind": "execution",
            "task_id": "task-1",
            "role": "developer",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
            "review_verdict": "RETURN",
            "rework_rounds": 1,
            "owner_interventions": 0,
        }
    )
    result = run_state(tmp_path, "observe", observation)
    assert result.returncode == 1
    assert "execution' observations must not set task-only field(s)" in result.stderr
    assert "review_verdict" in result.stderr
    assert "rework_rounds" in result.stderr
    assert "owner_interventions" in result.stderr


def test_observe_task_rejects_execution_only_fields(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")
    observation = json.dumps(
        {
            "kind": "task",
            "task_type": "implementation",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
        }
    )
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 1
    assert "task' observations must not set execution-only field(s)" in result.stderr
    assert "harness" in result.stderr
    assert "model" in result.stderr


def test_observe_task_kind_updates_task_aggregate_not_combinations(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")

    observation = json.dumps(
        {
            "kind": "task",
            "task_type": "implementation",
            "completed": True,
            "owner_interventions": 1,
            "review_verdict": "APPROVE",
        }
    )
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 0, result.stderr

    aggregates = json.loads(
        (tmp_path / "state" / "orca-orchestrator" / "aggregates.json").read_text()
    )
    assert aggregates["combinations"] == {}
    assert aggregates["role_combinations"] == {}
    task_bucket = aggregates["tasks"]["implementation"]
    assert task_bucket["observations"] == 1
    assert task_bucket["completed"] == 1
    assert task_bucket["review_verdicts"] == {"APPROVE": 1}
    assert task_bucket["mean_rework_rounds"] == 0.0


def test_observe_task_kind_requires_task_id_flag(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    result = run_state(
        tmp_path, "observe", '{"kind":"task","task_id":"t1","task_type":"implementation"}'
    )
    assert result.returncode == 1
    assert "require --task-id" in result.stderr


def test_observe_task_kind_rejects_task_id_mismatch(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")
    observation = json.dumps(
        {"kind": "task", "task_id": "other-task", "task_type": "implementation"}
    )
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 1
    assert "does not match --task-id" in result.stderr


def test_observe_task_kind_requires_task_type(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")
    result = run_state(tmp_path, "observe", '{"kind":"task"}', "--task-id", "task-1")
    assert result.returncode == 1
    assert "task_type" in result.stderr


def test_observe_task_kind_requires_task_started(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    observation = json.dumps({"kind": "task", "task_type": "implementation"})
    result = run_state(tmp_path, "observe", observation, "--task-id", "never-started")
    assert result.returncode == 1
    assert "not started" in result.stderr


def test_observe_task_kind_requires_task_finished(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    assert run_task(tmp_path, "start", "task-1").returncode == 0
    observation = json.dumps({"kind": "task", "task_type": "implementation"})
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 1
    assert "is not finished" in result.stderr


def test_observe_task_kind_rejects_duplicate_task_observation(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")
    observation = json.dumps({"kind": "task", "task_type": "implementation"})
    assert run_state(tmp_path, "observe", observation, "--task-id", "task-1").returncode == 0

    duplicate = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert duplicate.returncode == 1
    assert "already has a recorded 'task' observation" in duplicate.stderr


def test_observe_with_task_id_fills_counters_from_task_state(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    assert run_task(tmp_path, "start", "task-1").returncode == 0
    assert run_task(tmp_path, "record", "task-1", "--event", "rework").returncode == 0
    assert run_task(tmp_path, "record", "task-1", "--event", "rework").returncode == 0
    assert run_task(tmp_path, "record", "task-1", "--event", "dispatch").returncode == 0
    assert (
        run_task(tmp_path, "finish", "task-1", "--termination-reason", "rework_limit_reached")
        .returncode
        == 0
    )

    observation = json.dumps({"kind": "task", "task_type": "implementation", "completed": True})
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 0, result.stderr

    obs_path = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"
    row = json.loads(obs_path.read_text().splitlines()[0])
    assert row["task_id"] == "task-1"
    assert row["rework_rounds"] == 2
    assert row["dispatches"] == 1
    assert row["termination_reason"] == "rework_limit_reached"


def test_observe_with_task_id_rejects_caller_supplied_derived_counters(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")

    observation = json.dumps(
        {"kind": "task", "task_type": "implementation", "rework_rounds": 999}
    )
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 1
    assert "must not set task-only field(s)" in result.stderr
    assert "rework_rounds" in result.stderr


def test_observe_with_task_id_fails_if_task_not_started(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    observation = json.dumps({"kind": "task", "task_type": "implementation"})
    result = run_state(tmp_path, "observe", observation, "--task-id", "never-started")
    assert result.returncode == 1
    assert "not started" in result.stderr


def test_execution_observation_with_task_id_stamps_task_id_without_requiring_task_file(
    tmp_path: Path,
) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    observation = json.dumps(
        {"kind": "execution", "role": "developer", "harness": "pi", "model": "qwen/qwen3-coder-next"}
    )
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 0, result.stderr
    row = json.loads(
        (tmp_path / "state" / "orca-orchestrator" / "observations.jsonl").read_text().splitlines()[0]
    )
    assert row["task_id"] == "task-1"


def test_execution_observation_rejects_task_id_mismatch(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    observation = json.dumps(
        {
            "kind": "execution",
            "task_id": "other-task",
            "role": "developer",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
        }
    )
    result = run_state(tmp_path, "observe", observation, "--task-id", "task-1")
    assert result.returncode == 1
    assert "does not match --task-id" in result.stderr


def test_observe_compacts_oldest_combination_evidence_without_losing_aggregates(
    tmp_path: Path,
) -> None:
    assert run_state(tmp_path, "init").returncode == 0

    config = tmp_path / "config" / "orca-orchestrator" / "config.json"
    value = json.loads(config.read_text())
    value["compaction"]["max_active_observations_per_combination"] = 2
    value["compaction"]["archive_batch_size_per_combination"] = 1
    config.write_text(json.dumps(value))

    for index in range(3):
        observation = json.dumps(
            {
                "timestamp": f"2026-08-19T08:0{index}:00Z",
                "kind": "execution",
                "task_id": f"task-{index}",
                "role": "developer",
                "task_type": "implementation",
                "harness": "pi",
                "model": "qwen/qwen3-coder-next",
                "backend": "lmstudio",
                "completed": index != 0,
            }
        )
        result = run_state(tmp_path, "observe", observation)
        assert result.returncode == 0, result.stderr

    active_path = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"
    active = [json.loads(line) for line in active_path.read_text().splitlines()]
    assert len(active) == 2
    assert [item["timestamp"] for item in active] == [
        "2026-08-19T08:01:00Z",
        "2026-08-19T08:02:00Z",
    ]

    archives = list(
        (tmp_path / "state" / "orca-orchestrator" / "archive").glob(
            "observations-*.jsonl"
        )
    )
    assert len(archives) == 1
    archived = [json.loads(line) for line in archives[0].read_text().splitlines()]
    assert [item["timestamp"] for item in archived] == ["2026-08-19T08:00:00Z"]

    aggregates = json.loads(
        (tmp_path / "state" / "orca-orchestrator" / "aggregates.json").read_text()
    )
    combo = aggregates["combinations"]["pi|qwen/qwen3-coder-next|lmstudio|none|none"]
    assert combo["observations"] == 3
    assert combo["completed"] == 2


def test_execution_and_task_observations_compact_in_separate_groups(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")

    config = tmp_path / "config" / "orca-orchestrator" / "config.json"
    value = json.loads(config.read_text())
    value["compaction"]["max_active_observations_per_combination"] = 1
    value["compaction"]["archive_batch_size_per_combination"] = 1
    config.write_text(json.dumps(value))

    execution = json.dumps(
        {
            "kind": "execution",
            "task_id": "task-1",
            "role": "developer",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
        }
    )
    task = json.dumps({"kind": "task", "task_type": "implementation"})
    assert run_state(tmp_path, "observe", execution).returncode == 0
    assert run_state(tmp_path, "observe", task, "--task-id", "task-1").returncode == 0

    active_path = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"
    active_kinds = {json.loads(line)["kind"] for line in active_path.read_text().splitlines()}
    assert active_kinds == {"execution", "task"}


def test_pre_split_observation_without_kind_is_rejected_on_read(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0

    observations_path = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"
    legacy_record = {
        "schema_version": 1,
        "timestamp": "2026-01-01T00:00:00Z",
        "task_type": "implementation",
        "harness": "pi",
        "model": "qwen/qwen3-coder-next",
        "review_verdict": "APPROVE",
    }
    observations_path.write_text(json.dumps(legacy_record) + "\n")

    result = run_state(tmp_path, "aggregate")
    assert result.returncode == 1
    assert "no valid 'kind'" in result.stderr

    compact_result = run_state(tmp_path, "compact")
    assert compact_result.returncode == 1
    assert "no valid 'kind'" in compact_result.stderr

    summary_result = run_state(tmp_path, "summary")
    assert summary_result.returncode == 1
    assert "no valid 'kind'" in summary_result.stderr


def test_manual_compact_is_noop_below_threshold(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    observation = json.dumps(
        {
            "kind": "execution",
            "task_id": "task-1",
            "role": "tester",
            "harness": "opencode",
            "model": "qwen/qwen3-coder-next",
        }
    )
    assert run_state(tmp_path, "observe", observation).returncode == 0

    result = run_state(tmp_path, "compact")
    assert result.returncode == 0, result.stderr
    assert "no compaction required" in result.stdout


def test_summary_empty_state(tmp_path: Path) -> None:
    assert run_state(tmp_path, "summary").returncode == 0

    result = run_state(tmp_path, "summary")
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["schema_version"] == 1
    assert "generated_at" in output
    assert output["tasks"]["active_count"] == 0
    assert output["tasks"]["finished_count"] == 0
    assert output["tasks"]["active"] == []
    assert output["observations"]["execution"] == 0
    assert output["observations"]["task"] == 0
    assert output["observations"]["total"] == 0
    assert output["observations"]["active_file"] == 0
    assert output["observations"]["archived"] == 0
    assert output["capabilities"]["present"] is False
    assert output["capabilities"]["updated_at"] is None
    assert output["capabilities"]["age_minutes"] is None
    assert output["aggregates"]["harnesses_tracked"] == 0
    assert output["aggregates"]["models_tracked"] == 0
    assert output["aggregates"]["combinations_tracked"] == 0
    assert output["aggregates"]["role_combinations_tracked"] == 0
    assert output["aggregates"]["task_types_tracked"] == 0
    assert output["role_combinations"] == {}


def test_summary_with_one_task_and_observations(tmp_path: Path) -> None:
    # For summary, tasks.show active tasks from tasks/<id>.json files
    # When a task is finished, it still exists but status="finished" means active_count=0
    # Let's test with an unfinished task to see it in the output

    assert run_state(tmp_path, "init").returncode == 0

    # Start a task but don't finish it yet
    result = run_task(tmp_path, "start", "task-1")
    assert result.returncode == 0

    # Add an execution observation
    observation = json.dumps(
        {
            "kind": "execution",
            "task_id": "task-1",
            "role": "developer",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
            "backend": "lmstudio",
            "completed": True,
        }
    )
    assert run_state(tmp_path, "observe", observation).returncode == 0

    # Add a task observation (task must be finished first)
    start_and_finish_task(tmp_path, "task-1")

    task_obs = json.dumps({"kind": "task", "task_type": "implementation", "completed": True})
    assert run_state(tmp_path, "observe", task_obs, "--task-id", "task-1").returncode == 0

    # Create capabilities.json directly (avoid discover.py for simplicity)
    caps_path = tmp_path / "state" / "orca-orchestrator" / "capabilities.json"
    caps_value = {
        "schema_version": 1,
        "updated_at": "2026-08-19T14:00:00Z",
        "tools": {},
        "backends": {},
        "cloud": {},
    }
    caps_path.write_text(json.dumps(caps_value))

    result = run_state(tmp_path, "summary")
    assert result.returncode == 0

    output = json.loads(result.stdout)
    assert output["schema_version"] == 1
    assert "generated_at" in output

    # Since we finished task-1, it's not active
    assert output["tasks"]["active_count"] == 0
    assert output["tasks"]["finished_count"] == 1

    # active list should be empty for finished tasks
    assert output["tasks"]["active"] == []

    # Check observations
    assert output["observations"]["execution"] == 1
    assert output["observations"]["task"] == 1
    assert output["observations"]["total"] == 2
    assert output["observations"]["active_file"] == 2
    assert output["observations"]["archived"] == 0

    # Check capabilities
    assert output["capabilities"]["present"] is True
    assert output["capabilities"]["updated_at"] == "2026-08-19T14:00:00Z"
    assert isinstance(output["capabilities"]["age_minutes"], float)
    assert output["capabilities"]["age_minutes"] > 0

    # Check aggregates
    assert output["aggregates"]["harnesses_tracked"] == 1
    assert output["aggregates"]["models_tracked"] == 1
    assert output["aggregates"]["combinations_tracked"] == 1
    assert output["aggregates"]["role_combinations_tracked"] == 1
    assert output["aggregates"]["task_types_tracked"] == 1

    role_combos = output["role_combinations"]
    assert len(role_combos) == 1
    key = "developer|pi|qwen/qwen3-coder-next|lmstudio|none|none"
    assert key in role_combos
    assert role_combos[key]["observations"] == 1


def test_summary_with_active_task(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    result = run_task(tmp_path, "start", "task-1")
    assert result.returncode == 0

    # Don't finish - keep it active

    caps_path = tmp_path / "state" / "orca-orchestrator" / "capabilities.json"
    caps_value = {
        "schema_version": 1,
        "updated_at": "2026-08-19T14:00:00Z",
        "tools": {},
        "backends": {},
        "cloud": {},
    }
    caps_path.write_text(json.dumps(caps_value))

    result = run_state(tmp_path, "summary")
    assert result.returncode == 0

    output = json.loads(result.stdout)
    assert output["tasks"]["active_count"] == 1
    assert output["tasks"]["finished_count"] == 0
    tasks = output["tasks"]["active"]
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "task-1"
    assert tasks[0]["status"] == "active"


def test_summary_human_format(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")
    result = run_state(tmp_path, "summary", "--human")
    assert result.returncode == 0
    assert not result.stdout.strip().startswith("{")
    assert "State summary" in result.stdout


def test_summary_does_not_mutate_state(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    start_and_finish_task(tmp_path, "task-1")

    obs = json.dumps({"kind": "execution", "task_id": "task-1", "role": "developer", "harness": "pi", "model": "qwen/qwen3-coder-next"})
    assert run_state(tmp_path, "observe", obs).returncode == 0
    caps_path = tmp_path / "state" / "orca-orchestrator" / "capabilities.json"
    caps_path.write_text(json.dumps({
        "schema_version": 1,
        "updated_at": "2026-08-19T14:00:00Z",
        "tools": {},
        "backends": {},
        "cloud": {},
    }))

    pre_files = {}
    for p in (tmp_path / "state" / "orca-orchestrator").rglob("*"):
        if p.is_file():
            pre_files[str(p)] = (p.read_text(), p.stat().st_mtime)

    result = run_state(tmp_path, "summary")
    assert result.returncode == 0

    for p in (tmp_path / "state" / "orca-orchestrator").rglob("*"):
        if p.is_file():
            content, mtime = pre_files[str(p)]
            assert p.read_text() == content
            assert p.stat().st_mtime == mtime
