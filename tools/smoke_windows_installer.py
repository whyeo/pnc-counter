"""Run the real guided setup against an isolated/installed private runtime.

Invoked by that runtime's python.exe with -I. Downloads PyTorch; accepts an
existing checkpoint to avoid downloading the same verified weights again.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path

from nucleus_analysis.managed_setup import hidden_options
from nucleus_analysis.preferences import load_preferences
from nucleus_analysis.setup_wizard import SetupWizard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--mode", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    if args.checkpoint:
        target = workdir / "models/sam2.1_hiera_tiny.pt"
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(args.checkpoint, target)
    root = tk.Tk()
    root.withdraw()
    preference_file = workdir / "preferences.json"
    wizard = SetupWizard(root, Path(sys.base_prefix), preference_file)
    started = time.monotonic()
    deadline = started + 1800
    while wizard.driver is None and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    wizard.mode.set(args.mode)
    wizard.model.set("tiny")
    wizard.start_button.invoke()
    last_status, last_update = None, 0
    while wizard.ready_python is None and time.monotonic() < deadline:
        root.update()
        status = wizard.status.get()
        if status != last_status or time.monotonic() - last_update > 30:
            print(f"{round(time.monotonic() - started)}s: {status}", flush=True)
            last_status, last_update = status, time.monotonic()
        if wizard.start_button.cget("text") == "Retry setup":
            raise RuntimeError(f"Setup failed: {status}; log={wizard.log_path}")
        time.sleep(.03)
    assert wizard.ready_python is not None, "Setup timed out"
    profile = load_preferences(preference_file)
    assert profile["managed_runtime"]["verified"]
    assert profile["hardware"]["device"] == args.mode
    python = wizard.ready_python
    for token in root.tk.call("after", "info"):
        root.after_cancel(token)
    root.destroy()
    # Fresh process verifies the saved launch path without importing Torch.
    check = "\n".join([
        "import sys,tkinter as tk",
        "from pathlib import Path",
        "from nucleus_analysis.gui import CounterApp",
        "r=tk.Tk(); r.withdraw()",
        f"a=CounterApp(r,preference_file=Path({str(preference_file)!r}))",
        "r.update()",
        "assert a.hardware is not None and not a.setup_busy",
        "assert 'torch' not in sys.modules",
        "assert a.drop_enabled",
        "print('Saved-runtime launch, native file drops and cached hardware passed')",
        "r.destroy()",
    ])
    subprocess.run([str(python), "-I", "-c", check], check=True, **hidden_options())
    result = {"mode": args.mode, "seconds": time.monotonic() - started, "python": str(python),
              "profile": profile["managed_runtime"], "hardware": profile["hardware"]}
    (workdir / "smoke-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
