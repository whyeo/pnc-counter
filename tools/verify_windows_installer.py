"""Install the release, open a public ND2 through Tk and export actual results.

Use --require-no-matlab on the clean Windows runner. The installed Python runs
with -I, and the test asserts it imported the installed app, never this checkout.
"""

import argparse
import inspect
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from release_metadata import digest

ROOT = Path(__file__).resolve().parents[1]


def matlab_inventory():
    found = {shutil.which("matlab")}
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = Path(os.environ.get(name, "C:/Program Files")) / "MATLAB"
        if base.is_dir():
            found.update(str(p) for p in base.glob("R*/bin/matlab.exe"))
    return sorted({os.path.normcase(str(p)) for p in found if p})


def fetch_sample(destination):
    spec = json.loads((ROOT / "installer/windows/smoke-sample.json").read_text(encoding="utf-8"))
    destination = Path(destination)
    if not destination.is_file() or digest(destination) != spec["sha256"]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(spec["url"], timeout=120) as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)
    if digest(destination) != spec["sha256"]:
        raise ValueError("Public ND2 fixture checksum failed")
    return spec


def installed_analysis(runtime, preferences, sample, output, report, expected_commit, sam):
    # Every import here is performed by the installed runtime in a separate process.
    import csv
    import json
    import time
    import tkinter as tk
    from pathlib import Path
    from unittest.mock import patch

    import nucleus_analysis
    from nucleus_analysis.gui import CounterApp

    runtime, output, report = Path(runtime), Path(output), Path(report)
    assert Path(nucleus_analysis.__file__).resolve().is_relative_to(runtime.resolve())
    manifest = json.loads((runtime / "pnc-runtime.json").read_text(encoding="utf-8"))
    if expected_commit:
        assert manifest["source"]["commit"] == expected_commit
        assert manifest["source"]["dirty"] is False
    if sam:
        import torch

        torch.set_num_threads(min(4, torch.get_num_threads()))
    root = tk.Tk()
    root.withdraw()
    app = CounterApp(root, preference_file=Path(preferences))
    errors = []
    root.report_callback_exception = lambda cls, error, tb: errors.append(str(error))

    def wait(condition, timeout=300):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            root.update()
            if errors:
                raise RuntimeError("; ".join(errors))
            time.sleep(.02)
        assert condition(), app.status.get()

    wait(lambda: app.hardware is not None and not app.setup_busy)
    app.values["backend"].set("sam2" if sam else "watershed")
    app.values["min_nucleus_area"].set("3")
    app.values["max_nucleus_area"].set("1024")
    app.values["points_per_side"].set("8")
    app.values["watershed_min_distance"].set("2")
    app.values["watershed_sigma"].set("1")
    app.output.set(str(output))
    # The upstream fixture has exactly two known channels; this confirmation is
    # part of the test protocol, not automatic biological marker inference.
    app.channel_dialog = lambda path, metadata: {"dapi_channel": 0, "pnc_channel": 1,
                                                "time_index": 0, "position_index": 0}
    with patch("nucleus_analysis.gui.filedialog.askopenfilenames", return_value=(sample,)):
        app.select_files()
    items = app.table.get_children()
    assert len(items) == 1 and app.table.set(items[0], "total") == ""
    wait(lambda: hasattr(app.preview, "image"))
    app.start()
    wait(lambda: app.status.get().startswith("Finished:"))
    assert app.failed == 0, app.status.get()
    assert app.table.get_children() == items and app.table.set(items[0], "status") == "Done"
    destination = app.output_by_item[items[0]]
    required = ["analysis.json", "nuclei.csv", "images.npz", "nuclei_masks.npz", "visualization.png"]
    assert all((destination / name).is_file() and (destination / name).stat().st_size for name in required)
    metadata = json.loads((destination / "analysis.json").read_text(encoding="utf-8"))
    with (output / "summary.csv").open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1 and int(rows[0]["n_total"]) == metadata["summary"]["n_total"]
    assert json.loads((output / "errors.json").read_text(encoding="utf-8")) == []
    record = {"passed": True, "source": manifest.get("source"), "matlab": manifest.get("matlab"),
              "version": nucleus_analysis.__version__, "backend": metadata["config"]["backend"],
              "summary": metadata["summary"], "exports": required, "native_file_drops": app.drop_enabled,
              "installed_module": str(Path(nucleus_analysis.__file__).resolve())}
    report.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    for token in root.tk.call("after", "info"):
        root.tk.call("after", "cancel", token)
    root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("--workdir", type=Path, default=ROOT / "validation/local/release-smoke")
    parser.add_argument("--require-no-matlab", action="store_true")
    parser.add_argument("--expected-commit")
    parser.add_argument("--setup-sam", action="store_true", help="Run real CPU setup and analyze with SAM")
    parser.add_argument("--preview", action="store_true", help="Verify the isolated preview installer")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Installer verification requires Windows")
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    inventory = matlab_inventory()
    record = {"matlab_installations": inventory, "matlab_absent": not inventory, "passed": False}
    (workdir / "machine.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    if args.require_no_matlab and inventory:
        raise RuntimeError("Full MATLAB is installed on this machine; a MATLAB-free verification cannot be claimed")
    record["sample"] = fetch_sample(workdir / "sample.nd2")
    install = workdir / "installed app"
    assert install.resolve().is_relative_to(workdir)
    import winreg

    identity = "D397F5FC-A509-4C44-8959-18247B83FDF1" if args.preview else "B9C4DC6E-A44E-4862-8DA6-14983A6C7773"
    key = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{" + identity + "}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as handle:
            if Path(winreg.QueryValueEx(handle, "InstallLocation")[0]).resolve() != install:
                raise RuntimeError("An existing PNC Counter installation must not be replaced by this test")
    except FileNotFoundError:
        pass
    options = {"creationflags": subprocess.CREATE_NO_WINDOW}
    subprocess.run([str(args.installer.resolve()), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS",
                    f"/DIR={install}", f"/LOG={workdir / 'install.log'}"], check=True, timeout=300, **options)
    try:
        python = install / "runtime/python.exe"
        preferences = workdir / "user-data/preferences.json"
        if args.setup_sam:
            subprocess.run([str(python), "-I", str(ROOT / "tools/smoke_windows_installer.py"),
                            "--workdir", str(preferences.parent), "--mode", "cpu"], check=True, timeout=1800, **options)
            profile = json.loads(preferences.read_text(encoding="utf-8"))
            python = Path(profile["managed_runtime"]["python"])
        parameters = [str(install / "runtime"), str(preferences), str(workdir / "sample.nd2"),
                      str(workdir / "exports"), str(workdir / "analysis-check.json"), args.expected_commit, args.setup_sam]
        code = inspect.getsource(installed_analysis) + f"\ninstalled_analysis(*{parameters!r})\n"
        subprocess.run([str(python), "-I", "-c", code], check=True, timeout=600, **options)
        record.update(json.loads((workdir / "analysis-check.json").read_text(encoding="utf-8")))
        record["installer_sha256"] = digest(args.installer)
    finally:
        assert install.resolve().is_relative_to(workdir)
        subprocess.run([str(install / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                        f"/LOG={workdir / 'uninstall.log'}"], check=True, timeout=300, **options)
        record["uninstall_passed"] = True
        (workdir / "verification.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
