from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import discover  # noqa: E402
import state as state_helper  # noqa: E402

DISCOVER_SCRIPT = SCRIPT_DIR / "discover.py"


def test_command_version_reports_unavailable_when_not_on_path(monkeypatch):
    monkeypatch.setattr(discover.shutil, "which", lambda name: None)
    assert discover.command_version(["missingtool", "--version"]) == {"available": False}


def test_command_version_reports_version_from_stdout(monkeypatch):
    monkeypatch.setattr(discover.shutil, "which", lambda name: "/usr/bin/footool")

    class FakeCompleted:
        stdout = "footool 1.2.3\n"
        stderr = ""
        returncode = 0

    monkeypatch.setattr(discover.subprocess, "run", lambda *a, **k: FakeCompleted())
    result = discover.command_version(["footool", "--version"])
    assert result == {
        "available": True,
        "path": "/usr/bin/footool",
        "version": "footool 1.2.3",
        "exit_code": 0,
    }


def test_command_version_reports_error_on_timeout(monkeypatch):
    monkeypatch.setattr(discover.shutil, "which", lambda name: "/usr/bin/slow")

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="slow", timeout=5)

    monkeypatch.setattr(discover.subprocess, "run", raise_timeout)
    result = discover.command_version(["slow", "--version"])
    assert result["available"] is True
    assert "error" in result


def test_lmstudio_models_reports_unavailable_on_connection_error(monkeypatch):
    def raise_error(*args, **kwargs):
        raise discover.urllib.error.URLError("connection refused")

    monkeypatch.setattr(discover.urllib.request, "urlopen", raise_error)
    result = discover.lmstudio_models()
    assert result["available"] is False
    assert "error" in result


def test_lmstudio_models_filters_to_llm_type_and_extracts_fields(monkeypatch):
    payload = {
        "models": [
            {
                "type": "llm",
                "key": "a/b",
                "display_name": "B",
                "architecture": "x",
                "format": "gguf",
                "quantization": {"name": "8bit"},
                "max_context_length": 4096,
                "capabilities": {"vision": False},
                "selected_variant": "a/b@8bit",
                "loaded_instances": [1],
            },
            {"type": "embedding", "key": "should-be-skipped"},
        ]
    }

    class FakeResponse(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        discover.urllib.request, "urlopen", lambda *a, **k: FakeResponse(json.dumps(payload))
    )
    result = discover.lmstudio_models()
    assert result["available"] is True
    assert [m["key"] for m in result["models"]] == ["a/b"]
    assert result["models"][0]["loaded"] is True


def test_cloud_auth_signal_detects_present_env_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = discover.cloud_auth_signal("pi")
    assert result["any_present"] is True
    assert result["present_env_vars"] == ["ANTHROPIC_API_KEY"]


def test_cloud_auth_signal_absent_when_no_env_vars_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = discover.cloud_auth_signal("pi")
    assert result["any_present"] is False
    assert result["present_env_vars"] == []


def test_cloud_auth_signal_unknown_harness_has_no_checked_vars():
    result = discover.cloud_auth_signal("unknown-harness")
    assert result == {
        "checked_env_vars": [],
        "any_present": False,
        "present_env_vars": [],
    }


def test_discover_includes_cloud_entry_only_for_available_tools(monkeypatch):
    def fake_command_version(command):
        return {"available": command[0] == "claude"}

    monkeypatch.setattr(discover, "command_version", fake_command_version)
    monkeypatch.setattr(discover, "lmstudio_models", lambda: {"available": False})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = discover.discover()
    assert set(result["cloud"]) == {"claude"}
    assert result["cloud"]["claude"]["effort_configurable"] is True
    assert result["cloud"]["claude"]["any_present"] is False


def test_write_capabilities_persists_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    state_helper.write_capabilities({"tools": {"orca": {"available": True}}, "backends": {}, "cloud": {}})

    path = state_helper.capabilities_path()
    assert path.exists()
    value = json.loads(path.read_text())
    assert value["schema_version"] == 1
    assert "updated_at" in value
    assert value["tools"]["orca"]["available"] is True


def run_discover_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    return subprocess.run(
        [sys.executable, str(DISCOVER_SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_cli_write_persists_capabilities_json(tmp_path: Path) -> None:
    result = run_discover_cli(tmp_path, "--write")
    assert result.returncode == 0, result.stderr

    stdout_payload = json.loads(result.stdout)
    assert set(stdout_payload) == {"tools", "backends", "cloud"}

    capabilities_path = tmp_path / "state" / "orca-orchestrator" / "capabilities.json"
    assert capabilities_path.exists()
    written = json.loads(capabilities_path.read_text())
    assert written["schema_version"] == 1
    assert written["tools"] == stdout_payload["tools"]


def test_cli_without_write_does_not_persist(tmp_path: Path) -> None:
    result = run_discover_cli(tmp_path)
    assert result.returncode == 0, result.stderr
    capabilities_path = tmp_path / "state" / "orca-orchestrator" / "capabilities.json"
    assert not capabilities_path.exists()
