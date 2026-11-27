"""Use the verified private analysis environment before importing the desktop UI."""

import argparse
import subprocess
import sys
from pathlib import Path

from .managed_setup import active_runtime, hidden_options, runtime_base
from .preferences import load_preferences, preferences_path


def launch(python, *, setup=False, preference_file=None):
    python = Path(python)
    windowed = python.with_name("pythonw.exe") if sys.platform == "win32" else python
    command = [str(windowed if windowed.is_file() else python), "-I", "-m", "nucleus_analysis.desktop_launcher"]
    if setup:
        command.append("--setup")
    if preference_file:
        command += ["--preferences", str(preference_file)]
    return subprocess.Popen(command, **hidden_options())


def main(argv=None):
    parser = argparse.ArgumentParser(description="PNC Counter desktop launcher")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--preferences", type=Path)
    args = parser.parse_args(argv)
    path = args.preferences or preferences_path()
    preferences = load_preferences(path)
    base = runtime_base()
    if base:
        python = active_runtime(preferences, base)
        if args.setup or (python is None and not preferences.get("setup_skipped")):
            from .setup_wizard import main as setup_main

            setup_main(base, path)
            return
        if python and Path(sys.executable).resolve() not in (python.resolve(), python.with_name("pythonw.exe").resolve()):
            launch(python, preference_file=path)
            return
    import tkinter as tk

    from .gui import CounterApp

    root = tk.Tk()
    CounterApp(root, preference_file=path)
    root.mainloop()


if __name__ == "__main__":
    main()
