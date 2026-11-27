"""Exercise the installed preview slider and immutable save using a saved analysis."""

import argparse
import json
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import nucleus_analysis
from nucleus_analysis.editor import ReviewEditor
from nucleus_analysis.review import ReviewSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    if args.runtime:
        assert Path(nucleus_analysis.__file__).resolve().is_relative_to(args.runtime.resolve())
    args.workdir.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda cls, value, traceback: errors.append(str(value))
    editor = ReviewEditor(root, args.analysis)
    editor.window.withdraw()
    originals = {i: mask.pixels.copy() for i, mask in editor.session.masks.items()}

    def wait(condition):
        deadline = time.monotonic()+120
        while not condition() and time.monotonic() < deadline:
            root.update()
            if errors:
                raise RuntimeError("; ".join(errors))
            time.sleep(.01)
        assert condition(), editor.status.get()

    timings = []
    try:
        with patch("nucleus_analysis.segmentation.Segmenter.generate", side_effect=AssertionError("SAM must not run")):
            prepared = None
            for level in (0., 50., 100.):
                started = time.perf_counter()
                editor.pnc_method.set("Background-aware (preview)")
                editor.pnc_sensitivity.set(level)
                editor.schedule_pnc_preview()
                wait(lambda: not editor.busy and editor.session.config.pnc_mode == "adaptive"
                     and editor.session.config.pnc_sensitivity == level)
                current = editor.session.counts()[0]
                if prepared is not None:
                    assert editor.session._adaptive_features is prepared
                    assert current["n_positive"] >= timings[-1]["counts"]["n_positive"]
                prepared = editor.session._adaptive_features
                timings.append({"sensitivity": level, "seconds": time.perf_counter()-started, "counts": current})
            assert all((editor.session.masks[i].pixels == pixels).all() for i, pixels in originals.items())
            previous = editor.directory
            editor.save_to(args.workdir / "revisions")
            wait(lambda: not editor.busy and editor.directory != previous)
            reopened = ReviewSession.open(editor.directory)
            assert reopened.config.pnc_sensitivity == 100
            assert reopened.counts()[0] == editor.session.counts()[0]
            assert (editor.directory / "spots.csv").is_file()
        report = {"passed": True, "version": nucleus_analysis.__version__, "installed_module": nucleus_analysis.__file__,
                  "sam_rerun": False, "geometry_unchanged": True, "slider": timings,
                  "saved_revision": str(editor.directory), "original_analysis": str(args.analysis.resolve())}
        (args.workdir / "slider-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if editor._pnc_worker:
            editor._pnc_worker.join(timeout=5)
        if editor._pnc_after:
            editor.window.after_cancel(editor._pnc_after)
        editor.window.after_cancel(editor._poll_id)
        root.destroy()


if __name__ == "__main__":
    main()
