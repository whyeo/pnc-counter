"""Exercise real Tk event handlers and asynchronous revision saving in hidden windows."""

import argparse
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from nucleus_analysis import AnalysisConfig, analyze
from nucleus_analysis.gui import CounterApp
from nucleus_analysis.imaging import project_array
from nucleus_analysis.output import export_result
from nucleus_analysis.review import ReviewSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("validation/local/editor-smoke"))
    args = parser.parse_args()
    dapi = np.arange(120 * 180, dtype=np.uint16).reshape(120, 180)
    pnc = np.zeros_like(dapi)
    pnc[10, 10:22] = 5000
    masks = []
    for y, x in [(10, 10), (50, 70)]:
        yy, xx = np.mgrid[y:y + 21, x:x + 21]
        masks.append(np.ravel_multi_index((yy.ravel(), xx.ravel()), dapi.shape))
    config = AnalysisConfig(backend="watershed", min_nucleus_area=100,
                            max_nucleus_area=2000, threshold_mode="global")
    result = analyze(project_array(np.stack([dapi, pnc]), "CYX"), config, masks)
    original = args.output / "original"
    export_result(result, original)
    root = tk.Tk()
    root.withdraw()
    app = CounterApp(root, preference_file=args.output / "preferences.json", initialize=False)
    item = app.table.insert("", "end", values=("synthetic", "Done", 1, 2, "50%"))
    app.output_by_item[item] = original
    app.table.selection_set(item)
    app.review_selected()
    editor = app.editors[-1]
    editor.window.withdraw()
    root.update()

    def click(x, y, state=0):
        editor.click(SimpleNamespace(x=x * editor.scale - editor.canvas.canvasx(0),
                                    y=y * editor.scale - editor.canvas.canvasy(0), state=state))

    click(15, 15)
    assert editor.selected == {1}
    editor.mark(rejected=True)
    assert editor.session.counts()[0]["n_total"] == 1
    editor.undo()
    assert editor.session.counts()[0]["n_total"] == 2
    editor.tool.set("Redraw")
    editor.change_tool()
    for x, y in [(10, 11), (30, 11), (30, 30), (10, 30)]:
        click(x, y)
    editor.finish_outline()
    assert editor.session.counts()[0]["n_positive"] == 0
    editor.tool.set("Add")
    editor.change_tool()
    for x, y in [(120, 80), (135, 80), (135, 95), (120, 95)]:
        click(x, y)
    editor.finish_outline()
    assert editor.session.counts()[0]["n_total"] == 3
    editor.mark(flagged=True)
    assert editor.session.counts()[0]["n_flagged"] == 1
    click(75, 55)
    assert editor.selected == {2}
    editor.tool.set("Split")
    editor.change_tool()
    for x, y in [(70, 50), (80, 50), (80, 70), (70, 70)]:
        click(x, y)
    editor.finish_outline()
    assert editor.session.counts()[0]["n_total"] == 4
    editor.merge()
    assert editor.session.counts()[0]["n_total"] == 3
    editor.undo()
    assert editor.session.counts()[0]["n_total"] == 4
    editor.redo()
    assert editor.session.counts()[0]["n_total"] == 3
    editor.zoom(1.25)
    click(15, 15)
    assert editor.selected == {1}
    editor.channel.set("PNC threshold")
    editor.render()
    editor.save_to(args.output / "reviews")
    deadline = time.monotonic() + 20
    while editor.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert not editor.busy, "Background revision save did not finish"
    assert not editor.session.dirty
    assert app.output_by_item[item] != original
    reopened = ReviewSession.open(app.output_by_item[item])
    assert reopened.counts()[0] == editor.session.counts()[0]
    assert app.table.item(item, "values")[3] == "3"
    editor.close()
    root.destroy()
    print("Tk selection, redraw, add, split/merge, rejection, flags, undo/redo, zoom, save/reopen and table update passed")


if __name__ == "__main__":
    main()
