from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "task.py"


def run_task(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
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


def task_file(tmp_path: Path, task_id: str) -> Path:
    return tmp_path / "state" / "orca-orchestrator" / "tasks" / f"{task_id}.json"


def test_start_snapshots_config_limits_and_zeroes_counters(tmp_path: Path) -> None:
    config = tmp_path / "config" / "orca-orchestrator" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "limits": {
                    "max_rework_rounds": 4,
                    "max_spec_revisions": 3,
                    "max_dispatches": 12,
                    "max_elapsed_minutes": 30,
                },
            }
        )
    )

    result = run_task(tmp_path, "start", "example-task")
    assert result.returncode == 0, result.stderr
    value = json.loads(task_file(tmp_path, "example-task").read_text())
    assert value["schema_version"] == 1
    assert value["status"] == "active"
    assert value["limits"] == {
        "max_rework_rounds": 4,
        "max_spec_revisions": 3,
        "max_dispatches": 12,
        "max_elapsed_minutes": 30,
    }
    assert value["counters"] == {
        "dispatches": 0,
        "rework_rounds": 0,
        "spec_revisions": 0,
        "technical_retries": 0,
        "blocking_timeouts": 0,
    }


def test_start_is_idempotent_without_resetting_state(tmp_path: Path) -> None:
    first = run_task(tmp_path, "start", "task")
    assert first.returncode == 0, first.stderr
    started_at = json.loads(first.stdout)["started_at"]
    assert run_task(tmp_path, "record", "task", "--event", "dispatch").returncode == 0

    second = run_task(
        tmp_path, "start", "task", "--limits-json", '{"max_dispatches": 99}'
    )
    assert second.returncode == 0, second.stderr
    value = json.loads(second.stdout)
    assert value["started_at"] == started_at
    assert value["counters"]["dispatches"] == 1
    assert value["limits"]["max_dispatches"] == 8


@pytest.mark.parametrize(
    ("event", "counter"),
    [
        ("dispatch", "dispatches"),
        ("rework", "rework_rounds"),
        ("spec_revision", "spec_revisions"),
        ("technical_retry", "technical_retries"),
        ("blocking_timeout", "blocking_timeouts"),
    ],
)
def test_record_increments_each_event(
    tmp_path: Path, event: str, counter: str
) -> None:
    assert run_task(tmp_path, "start", "task").returncode == 0
    result = run_task(tmp_path, "record", "task", "--event", event)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["counters"][counter] == 1


def test_record_rejects_unknown_event(tmp_path: Path) -> None:
    assert run_task(tmp_path, "start", "task").returncode == 0
    result = run_task(tmp_path, "record", "task", "--event", "unknown")
    assert result.returncode != 0
    assert "invalid choice" in result.stderr


def test_record_requires_started_active_task(tmp_path: Path) -> None:
    missing = run_task(tmp_path, "record", "missing", "--event", "dispatch")
    assert missing.returncode == 1
    assert "task 'missing' not started; run 'task.py start' first" in missing.stderr

    assert run_task(tmp_path, "start", "task").returncode == 0
    assert run_task(tmp_path, "finish", "task").returncode == 0
    finished = run_task(tmp_path, "record", "task", "--event", "dispatch")
    assert finished.returncode == 1
    assert "task 'task' is already finished" in finished.stderr


def test_status_reports_reached_and_null_limits(tmp_path: Path) -> None:
    result = run_task(
        tmp_path,
        "start",
        "task",
        "--limits-json",
        '{"max_dispatches": 1, "max_elapsed_minutes": null}',
    )
    assert result.returncode == 0, result.stderr
    assert run_task(tmp_path, "record", "task", "--event", "dispatch").returncode == 0
    status = run_task(tmp_path, "status", "task")
    assert status.returncode == 0, status.stderr
    value = json.loads(status.stdout)
    assert value["limit_reached"]["dispatches"] is True
    assert value["limit_reached"]["elapsed_minutes"] is False
    assert isinstance(value["elapsed_minutes"], float)


@pytest.mark.parametrize("task_id", ["", "a/b", "a\\b", "a..b"])
def test_invalid_task_ids_are_rejected(tmp_path: Path, task_id: str) -> None:
    result = run_task(tmp_path, "start", task_id)
    assert result.returncode == 1
    assert "error: task_id" in result.stderr


def test_limits_json_overrides_recognized_keys_only(tmp_path: Path) -> None:
    result = run_task(
        tmp_path, "start", "task", "--limits-json", '{"max_rework_rounds": 3}'
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["limits"]["max_rework_rounds"] == 3

    unknown = run_task(
        tmp_path, "start", "other", "--limits-json", '{"blocking_wait_minutes": 5}'
    )
    assert unknown.returncode == 1
    assert "unknown limit key(s): blocking_wait_minutes" in unknown.stderr


def test_finish_sets_completion_fields(tmp_path: Path) -> None:
    assert run_task(tmp_path, "start", "task").returncode == 0
    result = run_task(
        tmp_path, "finish", "task", "--termination-reason", "dispatch_limit_reached"
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["status"] == "finished"
    assert value["finished_at"].endswith("Z")
    assert value["termination_reason"] == "dispatch_limit_reached"
