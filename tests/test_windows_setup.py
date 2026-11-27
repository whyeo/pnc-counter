"""Guided setup regressions: isolation, failure recovery, activation and UI states."""

import json
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleus_analysis import managed_setup
from nucleus_analysis.preferences import load_preferences, save_preferences
from nucleus_analysis.setup_wizard import SetupWizard


@pytest.fixture
def setup_files(tmp_path, monkeypatch):
    base = tmp_path / "private Python"
    payload = base / "setup_payload"
    payload.mkdir(parents=True)
    (base / "pnc-runtime.json").write_text(json.dumps({"wheels": {}}))
    (payload / "constraints.txt").write_text("numpy==2.2.6")
    preferences = tmp_path / "user data/preferences.json"
    save_preferences(preferences, {"analysis": {"positive_threshold": 33}, "managed_runtime": {"old": True}})
    monkeypatch.setattr(managed_setup.shutil, "disk_usage", lambda p: SimpleNamespace(free=20 * 1024 ** 3))
    monkeypatch.setattr(managed_setup, "download_checkpoint", lambda model, target, progress:
                        (target.parent.mkdir(parents=True, exist_ok=True), target.write_bytes(b"checkpoint")))
    commands = []

    def runner(command, emit, cancel, log, **kwargs):
        commands.append(command)
        if "venv" in command:
            python = managed_setup.environment_python(command[-1])
            python.parent.mkdir(parents=True, exist_ok=True)
            python.touch()
        if "nucleus_analysis.setup_probe" in command:
            output = Path(command[-1])
            mode = command[command.index("--device") + 1]
            output.write_text(json.dumps({"ok": True, "device": mode, "hardware": {"device": mode, "name": "Test"}}))
    return base, preferences, commands, runner


@pytest.mark.parametrize("mode", ["cpu", "cuda"])
def test_private_setup_activates_only_after_model_verification(setup_files, mode):
    base, path, commands, runner = setup_files
    events = []
    python = managed_setup.setup_environment(base, path, mode, "tiny", lambda *e: events.append(e), runner=runner)
    saved = load_preferences(path)
    assert saved["managed_runtime"]["python"] == str(python.resolve())
    assert saved["managed_runtime"]["verified"] is True
    assert saved["analysis"]["positive_threshold"] == 33
    assert saved["analysis"]["sam2_model"] == "tiny"
    assert "setup_pending" not in saved
    assert [e[1][0] for e in events if e[0] == "stage"] == list(range(6))
    assert managed_setup.MODES[mode] in commands[1]
    assert commands[1][0] == python
    assert "--no-index" in commands[2]  # Bundled SAM installs without Git/network.
    assert all(Path(command[0]).name.lower() not in ("git", "git.exe") for command in commands)
    assert all(not str(value).startswith("git+") for command in commands for value in command)
    assert managed_setup.active_runtime(saved, base) == python.resolve()


def test_failed_setup_preserves_active_engine_and_retry_uses_pending_environment(setup_files):
    base, path, commands, runner = setup_files

    def failed(command, *args, **kwargs):
        runner(command, *args, **kwargs)
        if "torch==2.7.1" in command:
            raise RuntimeError("Connection interrupted")
    with pytest.raises(RuntimeError, match="Connection interrupted"):
        managed_setup.setup_environment(base, path, "cpu", "tiny", lambda *e: None, runner=failed)
    saved = load_preferences(path)
    assert saved["managed_runtime"] == {"old": True}
    pending = saved["setup_pending"]["directory"]
    commands.clear()
    python = managed_setup.setup_environment(base, path, "cpu", "tiny", lambda *e: None, runner=runner)
    assert python == managed_setup.environment_python(pending)
    assert not any("venv" in command for command in commands)


def test_cancel_before_activation_preserves_working_profile(setup_files):
    base, path, commands, runner = setup_files
    cancel = threading.Event()

    def install(command, *args, **kwargs):
        runner(command, *args, **kwargs)
        if "nucleus_analysis.setup_probe" in command:
            cancel.set()
    with pytest.raises(managed_setup.SetupCancelled):
        managed_setup.setup_environment(base, path, "cpu", "tiny", lambda *e: None, cancel, runner=install)
    assert load_preferences(path)["managed_runtime"] == {"old": True}


def test_invalid_verification_or_bundle_is_never_activated(setup_files):
    base, path, commands, runner = setup_files

    def invalid(command, *args, **kwargs):
        runner(command, *args, **kwargs)
        if "nucleus_analysis.setup_probe" in command:
            Path(command[-1]).write_text('{"ok": false}')
    with pytest.raises(ValueError, match="verification failed"):
        managed_setup.setup_environment(base, path, "cpu", "tiny", lambda *e: None, runner=invalid)
    assert load_preferences(path)["managed_runtime"] == {"old": True}
    (base / "pnc-runtime.json").write_text('{"wheels": {"../../unsafe": "bad"}}')
    with pytest.raises(ValueError, match="damaged"):
        managed_setup.setup_environment(base, path, "cpu", "tiny", lambda *e: None, runner=runner)


def test_active_environment_requires_base_and_python_abi(setup_files):
    base, path, commands, runner = setup_files
    python = managed_setup.setup_environment(base, path, "cpu", "tiny", lambda *e: None, runner=runner)
    preferences = load_preferences(path)
    assert managed_setup.active_runtime(preferences, base / "other") is None
    preferences["managed_runtime"]["python_abi"] = [3, 99]
    assert managed_setup.active_runtime(preferences, base) is None
    preferences["managed_runtime"]["python_abi"] = list(sys.version_info[:2])
    python.unlink()
    assert managed_setup.active_runtime(preferences, base) is None


@pytest.mark.parametrize("text,ready", [
    ("CUDA Version: 12.8", True), ("CUDA Version: 13.0", True),
    ("CUDA Version: 12.7", False), ("No devices found", False),
])
def test_driver_recommendation_does_not_import_torch(monkeypatch, text, ready):
    monkeypatch.setattr(managed_setup.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=text))
    assert managed_setup.probe_nvidia()["cuda_ready"] is ready


def test_process_cancellation_stops_only_its_child(tmp_path):
    cancel = threading.Event()
    timer = threading.Timer(.3, cancel.set)
    timer.start()
    try:
        with (tmp_path / "log.txt").open("w") as log, pytest.raises(managed_setup.SetupCancelled):
            managed_setup.run_command([sys.executable, "-u", "-c", "import time; print('working'); time.sleep(30)"],
                                      lambda *e: None, cancel, log)
    finally:
        timer.cancel()


@pytest.fixture
def wizard(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    monkeypatch.setattr("nucleus_analysis.setup_wizard.probe_nvidia", lambda: {
        "cuda_ready": True, "message": "Test GPU", "cuda_version": "12.8"})
    launched = []
    wizard = SetupWizard(root, tmp_path, tmp_path / "preferences.json", launch_app=lambda *a, **k: launched.append((a, k)))
    wizard.launched = launched
    yield wizard
    wizard.cancel.set()
    if wizard.worker:
        wizard.worker.join(timeout=5)
        assert not wizard.worker.is_alive()
    if root.winfo_exists():
        for token in root.tk.call("after", "info"):
            root.tk.call("after", "cancel", token)
        root.destroy()


def pump(root, condition):
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    assert condition()


def test_wizard_recommendation_install_and_retry(wizard):
    pump(wizard.root, lambda: wizard.driver is not None)
    assert wizard.mode.get() == "cuda"
    attempts = []

    def install(base, path, mode, model, emit, cancel):
        attempts.append(mode)
        if len(attempts) == 1:
            raise RuntimeError("Test interrupted connection")
        for i in range(6):
            emit("stage", (i, "Test stage"))
        return base / "python.exe"
    wizard.installer = install
    wizard.start_button.invoke()
    pump(wizard.root, lambda: wizard.start_button.cget("text") == "Retry setup")
    wizard.start_button.invoke()
    pump(wizard.root, lambda: wizard.ready_python is not None)
    assert attempts == ["cuda", "cuda"]
    assert wizard.progress.cget("value") == 5
    assert all(v.get().startswith("✓") for v in wizard.stages)


def test_wizard_hardware_recheck_switches_recommendation(wizard, monkeypatch):
    pump(wizard.root, lambda: wizard.driver is not None)
    monkeypatch.setattr("nucleus_analysis.setup_wizard.probe_nvidia", lambda: {
        "cuda_ready": False, "message": "CPU only", "cuda_version": None})
    wizard.detect_button.invoke()
    pump(wizard.root, lambda: wizard.driver_status.get() == "CPU only")
    assert wizard.mode.get() == "cpu" and "disabled" in wizard.gpu_choice.state()


def test_wizard_cancel_immediately_explains_what_is_happening(wizard):
    wizard.request_cancel()
    assert wizard.cancel.is_set()
    assert "Stopping setup" in wizard.status.get()


def test_windowed_python_shares_the_cached_hardware_signature(monkeypatch):
    from nucleus_analysis.preferences import runtime_signature

    monkeypatch.setattr(sys, "executable", "C:/private/Python/pythonw.exe")
    windowed = runtime_signature()
    monkeypatch.setattr(sys, "executable", "C:/private/Python/python.exe")
    assert runtime_signature() == windowed
