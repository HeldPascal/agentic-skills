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
    observations = tmp_path / "state" / "orca-orchestrator" / "observations.jsonl"

    assert config.exists()
    assert registry.exists()
    assert observations.exists()
    assert json.loads(config.read_text())["schema_version"] == 1
    assert json.loads(registry.read_text())["schema_version"] == 1


def test_observe_appends_observation(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0

    observation = json.dumps(
        {
            "task_type": "implementation",
            "harness": "pi",
            "model": "qwen/qwen3-coder-next",
            "completed": True,
            "owner_interventions": 0,
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


def test_observe_rejects_missing_required_fields(tmp_path: Path) -> None:
    assert run_state(tmp_path, "init").returncode == 0
    result = run_state(tmp_path, "observe", '{"task_type":"implementation"}')
    assert result.returncode == 1
    assert "missing required field" in result.stderr
