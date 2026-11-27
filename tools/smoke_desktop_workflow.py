"""Exercise first-run setup and an actual ND2/CUDA batch through the desktop API."""

import argparse
import json
import time
import tkinter as tk
from pathlib import Path

from nucleus_analysis.gui import CounterApp


def wait(root, condition, seconds=120):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    root.update()
    assert condition(), "Desktop task timed out"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("validation/local/desktop-v05"))
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    app = CounterApp(root, preference_file=args.output / "preferences.json")
    wait(root, lambda: app.hardware is not None and not app.setup_busy)
    assert app.get_config().device == "cuda", app.hardware
    app.output.set(str(args.output / "results"))
    app.values["sam2_model"].set("small")
    app.checkpoint.set(str(Path("models/sam2.1_hiera_small.pt").resolve()))
    paths = [Path(f"pnc_counting/testfiles/testfiles/IMG{i}.nd2").resolve() for i in (1, 2)]
    # These two channels were verified against the MATLAB baseline. Generic
    # TxRED is never auto-confirmed by the production app.
    confirmations = []
    app.channel_dialog = lambda path, meta: confirmations.append(meta["channels"]) or {
        "dapi_channel": 0, "pnc_channel": 1, "time_index": 0, "position_index": 0}
    app.add_paths(paths)
    items = app.table.get_children()
    assert all(app.table.set(item, "total") == "" for item in items)
    started = time.monotonic()
    app.start()
    wait(root, lambda: app.status.get().startswith("Finished:"))
    first = time.monotonic() - started
    assert app.failed == 0, app.status.get()
    assert [(app.table.set(i, "positive"), app.table.set(i, "total")) for i in items] == [("67", "74"), ("42", "45")]
    started = time.monotonic()
    app.start()
    wait(root, lambda: app.status.get().startswith("Finished:"))
    repeated = time.monotonic() - started
    assert app.table.get_children() == items and len(confirmations) == 1
    report = {"device": app.hardware["name"], "first_seconds": first,
              "cached_repeat_seconds": repeated, "confirmations": len(confirmations),
              "rows": [app.table.item(i, "values") for i in items]}
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    for token in root.tk.call("after", "info"):
        root.after_cancel(token)
    root.destroy()


if __name__ == "__main__":
    main()
