from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import doctor  # noqa: E402


def test_check_writable_true_for_existing_writable_dir(tmp_path):
    ok, detail = doctor.check_writable(tmp_path)
    assert ok is True
    assert str(tmp_path) in detail


def test_check_writable_walks_up_to_nearest_existing_parent(tmp_path):
    missing = tmp_path / "does" / "not" / "exist"
    ok, detail = doctor.check_writable(missing)
    assert ok is True
    assert str(tmp_path) in detail


def test_check_writable_false_when_target_not_writable(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.os, "access", lambda path, mode: False)
    ok, detail = doctor.check_writable(tmp_path)
    assert ok is False
    assert "not writable" in detail


def _prepare_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "config").mkdir()
    (tmp_path / "state").mkdir()


def test_main_ok_when_orca_and_a_worker_and_paths_available(tmp_path, monkeypatch, capsys):
    _prepare_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("orca", "claude") else None
    )

    exit_code = doctor.main()
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["ok"] is True


def test_main_not_ok_without_any_worker_tool(tmp_path, monkeypatch, capsys):
    _prepare_env(tmp_path, monkeypatch)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/orca" if name == "orca" else None)

    exit_code = doctor.main()
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert out["ok"] is False


def test_main_not_ok_without_orca(tmp_path, monkeypatch, capsys):
    _prepare_env(tmp_path, monkeypatch)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)

    exit_code = doctor.main()
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert out["ok"] is False


def test_main_not_ok_when_state_path_not_writable(tmp_path, monkeypatch, capsys):
    _prepare_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("orca", "claude") else None
    )
    doctor.state_root().mkdir(parents=True, exist_ok=True)

    real_access = doctor.os.access

    def fake_access(path, mode):
        if str(path) == str(doctor.state_root()):
            return False
        return real_access(path, mode)

    monkeypatch.setattr(doctor.os, "access", fake_access)

    exit_code = doctor.main()
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert out["ok"] is False
