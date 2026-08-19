from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "state.py"


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


def test_init_creates_expected_files(tmp_path: Path) -> None:
    result = run_state(tmp_path, "init")
    assert result.returncode == 0, result.stderr

    config = tmp_path / "config" / "orca-orchestrator" / "config.json"
    registry = tmp_path / "state" / "orca-orchestrator" / "registry.json"
    aggregates = tmp_path / "state" / "orca-orchestrator" / "aggregates.json"
    observations = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"
    archive = tmp_path / "state" / "orca-orchestrator" / "archive"

    assert config.exists()
    assert registry.exists()
    assert aggregates.exists()
    assert observations.exists()
    assert archive.is_dir()

    config_value = json.loads(config.read_text())
    assert config_value["schema_version"] == 1
    assert config_value["limits"]["max_rework_rounds"] == 2
    assert config_value["limits"]["max_spec_revisions"] == 1
    assert config_value["limits"]["max_dispatches"] == 8
    assert config_value["compaction"]["max_active_observations_per_combination"] == 50
    assert json.loads(registry.read_text())["schema_version"] == 1
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


def test_observe_appends_observation_and_updates_aggregates(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0

    observation = json.dumps(
        {
            "task_type": "implementation",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
            "backend": "lmstudio",
            "completed": True,
            "owner_interventions": 0,
            "review_verdict": "RETURN",
            "rework_rounds": 1,
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
    combo = aggregates["combinations"]["pi|qwen/qwen3-coder-next|lmstudio"]
    assert combo["observations"] == 1
    assert combo["completed"] == 1
    assert combo["completion_rate"] == 1.0
    assert combo["review_verdicts"] == {"RETURN": 1}
    assert combo["mean_rework_rounds"] == 1.0


def test_observe_rejects_missing_required_fields(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    result = run_state(tmp_path, "observe", '{"task_type":"implementation"}')
    assert result.returncode == 1
    assert "missing required field" in result.stderr


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
    combo = aggregates["combinations"]["pi|qwen/qwen3-coder-next|lmstudio"]
    assert combo["observations"] == 3
    assert combo["completed"] == 2


def test_manual_compact_is_noop_below_threshold(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    observation = json.dumps(
        {
            "task_type": "implementation",
            "harness": "opencode",
            "model": "qwen/qwen3-coder-next",
        }
    )
    assert run_state(tmp_path, "observe", observation).returncode == 0

    result = run_state(tmp_path, "compact")
    assert result.returncode == 0, result.stderr
    assert "no compaction required" in result.stdout
