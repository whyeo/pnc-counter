"""Small, versioned desktop preferences; hardware probing is explicitly separate."""

import importlib.metadata
import importlib.util
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def preferences_path():
    from . import __version__

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    name = "PNC Counter Preview" if ".dev" in __version__ else "PNC Counter"
    return base / name / "preferences.json"


def runtime_signature():
    """Distribution metadata only: never import Torch on a cached launch."""
    versions = {}
    for package in ("torch", "SAM-2", "numpy"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return {"python": str(executable), "version": platform.python_version(),
            "platform": platform.platform(), "packages": versions}


def load_preferences(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != 1:
            return {"schema": 1}
        if not isinstance(data.get("channel_mappings", {}), dict):
            data["channel_mappings"] = {}
        return data
    except (OSError, ValueError):
        return {"schema": 1}


def save_preferences(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({**data, "schema": 1}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def cached_hardware(preferences):
    profile = preferences.get("hardware")
    if isinstance(profile, dict) and profile.get("runtime") == runtime_signature():
        if profile.get("device") in ("cpu", "cuda", "mps") and isinstance(profile.get("name"), str):
            return profile
    return None


def detect_hardware():
    profile = {"runtime": runtime_signature(), "device": "cpu", "name": "CPU",
               "detected_at": datetime.now(timezone.utc).isoformat(),
               "sam2_installed": importlib.util.find_spec("sam2") is not None}
    try:
        import torch

        if torch.cuda.is_available():
            # Availability alone can succeed with an incompatible driver/GPU wheel.
            test = torch.ones(8, device="cuda")
            assert (test * test).sum().item() == 8
            torch.cuda.synchronize()
            profile.update(device="cuda", name=torch.cuda.get_device_name(0),
                           memory_bytes=torch.cuda.get_device_properties(0).total_memory)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            assert torch.ones(8, device="mps").sum().item() == 8
            profile.update(device="mps", name="Apple GPU")
    except Exception as exc:
        profile["detail"] = str(exc)
    return profile


def find_checkpoint(model, preferred=None, roots=()):
    candidates = [Path(preferred)] if preferred else []
    candidates += [Path(root) / f"sam2.1_hiera_{model}.pt" for root in roots]
    return next((str(p.resolve()) for p in candidates if p.is_file()), "")
