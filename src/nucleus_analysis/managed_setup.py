"""Install SAM into a separate environment, activating it only after verification."""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from .preferences import load_preferences, save_preferences
from .setup_model import checksum, download_checkpoint

TORCH_VERSION = "2.7.1"
VISION_VERSION = "0.22.1"
SAM_REVISION = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
MODES = {"cpu": "https://download.pytorch.org/whl/cpu",
         "cuda": "https://download.pytorch.org/whl/cu128"}


class SetupCancelled(Exception):
    pass


def hidden_options():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def runtime_base():
    base = Path(sys.base_prefix)
    return base if (base / "pnc-runtime.json").is_file() else None


def probe_nvidia():
    """Driver inspection without importing Torch or downloading anything."""
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True,
                                timeout=8, check=False, **hidden_options())
        version = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", result.stdout)
        capable = bool(result.returncode == 0 and version and tuple(map(int, version.groups())) >= (12, 8))
        return {"cuda_ready": capable, "cuda_version": ".".join(version.groups()) if version else None,
                "message": ("Compatible NVIDIA driver detected. GPU processing is recommended." if capable else
                            "No NVIDIA driver with CUDA 12.8 support detected. CPU processing is available.")}
    except (OSError, subprocess.TimeoutExpired):
        return {"cuda_ready": False, "cuda_version": None,
                "message": "No usable NVIDIA driver detected. CPU processing is available."}


def environment_python(directory):
    return Path(directory) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def active_runtime(preferences, base):
    profile = preferences.get("managed_runtime")
    if not isinstance(profile, dict) or profile.get("verified") is not True:
        return None
    try:
        if Path(profile["base"]).resolve() != Path(base).resolve():
            return None
        if profile.get("python_abi") != list(sys.version_info[:2]):
            return None
        python = Path(profile["python"])
        return python if python.is_file() else None
    except (KeyError, TypeError, ValueError):
        return None


def run_command(command, emit, cancel, log, *, environment=None):
    """Stream output off the GUI thread and terminate only our own process tree."""
    import queue

    if cancel.is_set():
        raise SetupCancelled()
    options = hidden_options()
    if sys.platform != "win32":
        options["start_new_session"] = True
    process = subprocess.Popen([str(p) for p in command], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                               env=environment, **options)
    job = None
    if sys.platform == "win32":
        from .windows_process import ProcessJob

        try:
            job = ProcessJob(process)
        except OSError:
            pass  # Restricted hosts can deny jobs; taskkill is the fallback.
    lines = queue.Queue()

    def read():
        try:
            for line in process.stdout:
                lines.put(line.rstrip())
        finally:
            lines.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        while True:
            if cancel.is_set():
                raise SetupCancelled()
            try:
                line = lines.get(timeout=.15)
            except queue.Empty:
                continue
            if line is None:
                break
            log.write(line + "\n")
            log.flush()
            emit("detail", line)
        code = process.wait()
        if code:
            raise RuntimeError(f"Installation step exited with code {code}. See setup details or the saved log.")
    finally:
        if process.poll() is None:
            if sys.platform == "win32":
                if job:
                    job.terminate()
                else:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **hidden_options())
                    if process.poll() is None:
                        process.kill()
            else:
                import signal

                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=15)
        reader.join(timeout=2)
        if not reader.is_alive():
            process.stdout.close()
        if job:
            job.close()


def setup_environment(base, preference_file, mode, model, emit, cancel=None, runner=run_command):
    """Never modify a working environment or existing analysis thresholds."""
    if mode not in MODES or model not in ("tiny", "small"):
        raise ValueError("Choose CPU/NVIDIA processing and a Tiny/Small model")
    base, preference_file = Path(base), Path(preference_file)
    manifest = json.loads((base / "pnc-runtime.json").read_text(encoding="utf-8"))
    payload = base / "setup_payload"
    for name, expected in manifest["wheels"].items():
        if Path(name).name != name or checksum(payload / name) != expected:
            raise ValueError("The bundled SAM package is damaged. Reinstall PNC Counter.")
    cancel = cancel or threading.Event()
    root = preference_file.parent
    root.mkdir(parents=True, exist_ok=True)
    # CUDA wheels plus their extracted libraries need several gigabytes.
    if shutil.disk_usage(root).free < (12 if mode == "cuda" else 2) * 1024 ** 3:
        raise ValueError("Insufficient free disk space for the selected analysis engine (12 GB GPU / 2 GB CPU).")
    preferences = load_preferences(preference_file)
    pending = preferences.get("setup_pending", {})
    directory = Path(pending.get("directory", root / "runtimes" / f"{mode}-{uuid.uuid4().hex[:12]}"))
    if (not directory.resolve().is_relative_to((root / "runtimes").resolve())
            or pending.get("mode") != mode or pending.get("base") != str(base.resolve())):
        directory = root / "runtimes" / f"{mode}-{uuid.uuid4().hex[:12]}"
    python = environment_python(directory)
    preferences["setup_pending"] = {"directory": str(directory), "mode": mode, "base": str(base.resolve())}
    save_preferences(preference_file, preferences)
    logs = root / "setup-logs"
    logs.mkdir(exist_ok=True)
    log_path = logs / f"setup-{time.strftime('%Y%m%d-%H%M%S')}.log"
    emit("log", str(log_path))
    environment = dict(os.environ, PYTHONUTF8="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    # Respect institutional proxy/certificate configuration; never disable TLS verification.
    with log_path.open("a", encoding="utf-8") as log:
        def run(arguments):
            runner(arguments, emit, cancel, log, environment=environment)

        emit("stage", (0, "Preparing your private analysis environment"))
        if not python.is_file():
            run([base / ("python.exe" if sys.platform == "win32" else "bin/python3"), "-I", "-m", "venv",
                 "--system-site-packages", directory])
        emit("stage", (1, "Installing PyTorch — this download may take several minutes"))
        run([python, "-I", "-m", "pip", "install", "--no-cache-dir", "--progress-bar=off", "--constraint", payload / "constraints.txt",
             f"torch=={TORCH_VERSION}", f"torchvision=={VISION_VERSION}", "--index-url", MODES[mode]])
        emit("stage", (2, "Installing Meta SAM 2.1"))
        run([python, "-I", "-m", "pip", "install", "--no-index", "--find-links", payload,
             "--constraint", payload / "constraints.txt", "SAM-2==1.0"])
        emit("stage", (3, "Downloading and checking the selected model"))
        target = root / "models" / f"sam2.1_hiera_{model}.pt"

        def download_progress(text):
            if cancel.is_set():
                raise SetupCancelled()
            emit("download", text)
        if cancel.is_set():
            raise SetupCancelled()
        download_checkpoint(model, target, download_progress)
        emit("stage", (4, "Checking that the model runs on your computer"))
        report = directory / "verification.json"
        run([python, "-I", "-m", "nucleus_analysis.setup_probe", "--checkpoint", target,
             "--model", model, "--device", mode, "--output", report])
        verified = json.loads(report.read_text(encoding="utf-8"))
        if verified.get("ok") is not True or verified.get("device") != mode:
            raise ValueError("Analysis engine verification failed; the previous setup is preserved.")
        if cancel.is_set():
            raise SetupCancelled()
        preferences = load_preferences(preference_file)
        preferences["managed_runtime"] = {"python": str(python.resolve()), "base": str(base.resolve()),
                                          "python_abi": list(sys.version_info[:2]), "verified": True,
                                          "mode": mode, "sam_revision": SAM_REVISION}
        preferences["hardware"] = verified["hardware"]
        analysis = preferences.setdefault("analysis", {})
        analysis.update(backend="sam2", sam2_model=model, checkpoint=str(target.resolve()), device=mode)
        preferences.update(device_choice="auto", setup_skipped=False)
        preferences.pop("setup_pending", None)
        save_preferences(preference_file, preferences)
        emit("stage", (5, "Ready — setup has been saved for future launches"))
        return python
