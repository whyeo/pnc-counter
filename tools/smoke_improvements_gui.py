"""Hidden-window check of calibration/spot options, queue, notes and reference export."""

import argparse
import json
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk

import numpy as np
from skimage.draw import disk

from nucleus_analysis import AnalysisConfig, analyze
from nucleus_analysis.benchmark import benchmark
from nucleus_analysis.gui import CounterApp
from nucleus_analysis.imaging import project_array
from nucleus_analysis.output import export_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("validation/local/improvements-smoke"))
    args = parser.parse_args()
    dapi = np.zeros((100, 160), dtype=np.uint16)
    pnc = np.zeros_like(dapi)
    masks = []
    for y, x, size in [(20, 20, 35), (60, 105, 25), (0, 135, 15)]:
        dapi[y:y + size, x:x + size] = 2000
        yy, xx = np.mgrid[y:y + size, x:x + size]
        masks.append(np.ravel_multi_index((yy.ravel(), xx.ravel()), dapi.shape))
    for center in [(30, 30), (42, 42)]:
        rr, cc = disk(center, 3, shape=pnc.shape)
        pnc[rr, cc] = 5000
    p = project_array(np.stack([dapi, pnc]), "CYX", metadata={"pixel_size_um": {"x": 0.5, "y": 0.25}})
    root = tk.Tk()
    root.withdraw()
    app = CounterApp(root, preference_file=args.output / "preferences.json", initialize=False)
    app.config = AnalysisConfig(backend="watershed", threshold_mode="global")
    for name, var in app.values.items():
        value = getattr(app.config, name)
        var.set("" if value is None else str(value))
    app.advanced_settings()
    dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    dialog.withdraw()
    for name, text in {"border_policy": "exclude", "min_nucleus_area_um2": "40",
                       "max_nucleus_area_um2": "200", "pnc_mode": "spots", "min_spot_count": "2"}.items():
        app.values[name].set(text)
    buttons = dialog.winfo_children()[-1]
    next(w for w in buttons.winfo_children() if isinstance(w, ttk.Button) and w.cget("text") == "Save settings").invoke()
    config = app.get_config()
    assert config.pnc_mode == "spots" and config.border_policy == "exclude"
    assert config.min_nucleus_area_um2 == 40
    result = analyze(p, config, masks)
    assert result.basic_stats["n_total"] == 2 and result.basic_stats["n_positive"] == 1
    original = args.output / "predictions"
    export_result(result, original)
    item = app.table.insert("", "end", values=("synthetic", "Done", 1, 2, "50%"))
    app.output_by_item[item] = original
    app.table.selection_set(item)
    app.review_selected()
    editor = app.editors[-1]
    editor.window.withdraw()
    root.update()
    editor.queue_filter.set("uncertain")
    editor.refresh()
    editor.next_in_queue()
    assert len(editor.selected) == 1
    selected = next(iter(editor.selected))
    assert editor.session.counts()[1][selected]["border"]
    editor.edit_details()
    details = next(w for w in editor.window.winfo_children() if isinstance(w, tk.Toplevel))
    details.withdraw()
    widgets = details.winfo_children()
    entry = next(w for w in widgets if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
    entry.insert(0, "Synthetic test reviewer")
    notes = next(w for w in widgets if isinstance(w, tk.Text))
    notes.insert("1.0", "Partial nucleus excluded by border protocol")
    next(w for w in widgets if isinstance(w, ttk.Button)).invoke()
    assert editor.session.masks[selected].note.startswith("Partial nucleus")
    editor.selected = set(editor.session.masks)
    editor.mark(reviewed=True)
    assert not editor.session.review_queue("unreviewed")
    answers = iter(["Synthetic test reviewer", "synthetic-specimen-A", "test"])
    original_ask, original_folder = simpledialog.askstring, filedialog.askdirectory
    simpledialog.askstring = lambda *_a, **_kw: next(answers)
    filedialog.askdirectory = lambda *_a, **_kw: str(args.output / "references")
    try:
        editor.add_reference()
    finally:
        simpledialog.askstring, filedialog.askdirectory = original_ask, original_folder
    deadline = time.monotonic() + 20
    while editor.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert not editor.busy and not editor.session.dirty
    manifest = args.output / "references/manifest.json"
    assert json.loads(manifest.read_text())["cases"][0]["reviewer"] == "Synthetic test reviewer"
    report = benchmark(manifest, original)
    assert report["instance_f1"] == report["pnc_f1"] == 1
    editor.close()
    root.destroy()
    print("GUI physical/spot options, uncertainty queue, reviewer notes, confirmation, reference export and benchmark passed")


if __name__ == "__main__":
    main()
