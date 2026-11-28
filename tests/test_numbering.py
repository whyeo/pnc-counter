import csv
import json
import time

import numpy as np

from nucleus_analysis import AnalysisConfig, analyze
from nucleus_analysis.editor import ReviewEditor
from nucleus_analysis.imaging import project_array
from nucleus_analysis.numbering import spatial_numbering
from nucleus_analysis.output import export_result
from nucleus_analysis.review import ReviewSession


def example():
    shape = (100, 130)
    image = np.full(shape, 100, np.uint16)
    projections = project_array(np.stack([image, image]), "CYX")
    masks = []
    for y, x in ((70, 20), (22, 90), (20, 10)):
        yy, xx = np.mgrid[y:y+11, x:x+11]
        masks.append(np.ravel_multi_index((yy.ravel(), xx.ravel()), shape))
    return analyze(projections, AnalysisConfig(backend="watershed", min_nucleus_area=10),
                   masks=masks, mask_ids=[3, 9, 55])


def test_spatial_rows_do_not_sort_by_id_or_exact_y_and_are_deterministic():
    rows = [{"MaskID": i, "Area": 100, "CentroidX": x, "CentroidY": y}
            for i, x, y in [(90, 5, 13), (2, 35, 10), (70, 8, 40), (1, 34, 41)]]
    mapping, tolerance = spatial_numbering(rows)
    assert 5 < tolerance < 6
    assert [r["MaskID"] for r in mapping] == [90, 2, 70, 1]
    assert [r["Row"] for r in mapping] == [1, 1, 2, 2]
    assert spatial_numbering(reversed(rows)) == (mapping, tolerance)
    assert spatial_numbering([]) == ([], 0.)


def test_tied_centroids_and_staggered_rows_have_stable_order():
    rows = [{"MaskID": i, "Area": 100, "CentroidX": 10, "CentroidY": y}
            for i, y in [(9, 10), (3, 10), (7, 15), (1, 20)]]
    mapping, _ = spatial_numbering(rows)
    assert [r["MaskID"] for r in mapping] == [3, 9, 7, 1]
    assert [r["Row"] for r in mapping] == [1, 1, 1, 2]


def test_export_and_revision_mapping_preserve_mask_identity_and_geometry(tmp_path):
    result = example()
    original = tmp_path / "original"
    before_stats = [dict(r) for r in result.full_stats]
    export_result(result, original)
    assert result.full_stats == before_stats
    with (original / "nucleus_numbering.csv").open() as handle:
        mapping = list(csv.DictReader(handle))
    assert [(int(r["DisplayNumber"]), int(r["MaskID"])) for r in mapping] == [(1, 55), (2, 9), (3, 3)]
    metadata = json.loads((original / "analysis.json").read_text())
    assert metadata["nucleus_numbering"]["includes_excluded"]
    with (original / "nuclei.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert {int(r["MaskID"]):int(r["DisplayNumber"]) for r in rows} == {55:1,9:2,3:3}
    protected = {p.name: p.read_bytes() for p in original.iterdir()}
    session = ReviewSession.open(original)
    assert session.display_numbers == {55:1,9:2,3:3}
    session.mark([55], rejected=True, pnc_override=True)
    assert session.display_numbers == {55:1,9:2,3:3}
    new = session.add([(0, 0), (5, 0), (5, 5), (0, 5)])
    assert new == 56 and session.display_numbers == {56:1,55:2,9:3,3:4}
    session.undo()
    assert session.display_numbers == {55:1,9:2,3:3}
    path, _ = session.save(tmp_path / "reviews")
    reopened = ReviewSession.open(path)
    assert reopened.display_numbers == session.display_numbers
    for identifier in session.masks:
        np.testing.assert_array_equal(reopened.masks[identifier].pixels, session.masks[identifier].pixels)
    assert reopened.masks[55].rejected and reopened.masks[55].pnc_override
    assert all((original / name).read_bytes() == data for name, data in protected.items())


def test_native_side_panel_visibility_calls_numbering_and_drawing(tk_window, tmp_path):
    export_result(example(), tmp_path / "analysis")
    editor = ReviewEditor(tk_window, tmp_path / "analysis")
    editor.window.geometry("950x650")
    try:
        tk_window.update()
        assert not editor._initial_fit_pending
        h, w = editor.session.shape
        assert w * editor.scale <= editor.canvas.winfo_width() + 1
        assert h * editor.scale <= editor.canvas.winfo_height() + 1
        assert editor.pnc_left_label.winfo_rootx() == editor.pnc_slider.winfo_rootx()
        assert abs(editor.pnc_right_label.winfo_rootx() + editor.pnc_right_label.winfo_width()
                   - editor.pnc_slider.winfo_rootx() - editor.pnc_slider.winfo_width()) <= 1
        editor.zoom(1.25)
        zoomed = editor.scale
        editor.window.withdraw()
        editor.window.deiconify()
        tk_window.update()
        assert editor.scale == zoomed  # Remapping must preserve deliberate zoom.
        assert editor.list_ids == [55, 9, 3]
        assert editor.listbox.get(0).startswith("1:")
        bottom = editor.window.winfo_rooty() + editor.window.winfo_height()
        for widget in (editor.save_button, editor.enrichment_entry, editor.exclude_button,
                       editor.check_button, editor.more_button, *editor.call_buttons):
            assert widget.winfo_viewable()
            assert widget.winfo_rooty() + widget.winfo_height() <= bottom
        editor.selected = {55}
        editor.refresh()
        assert editor.selection_summary.get().startswith("Nucleus 1")
        editor.call_buttons[0].invoke()
        assert editor.session.masks[55].pnc_override is True
        assert editor.session.counts()[0]["n_positive"] == 1
        editor.toggle_exclusion()
        assert editor.session.counts()[0]["n_total"] == 2
        editor.undo()
        assert editor.session.counts()[0]["n_total"] == 3
        editor.check_and_next()
        assert editor.session.masks[55].reviewed and editor.selected == {9}
        editor.next_in_queue(-1)
        assert editor.selected == {55}
        editor.pnc_enrichment.set(1.8123456)
        editor.schedule_pnc_preview("1.8123456")
        assert editor.enrichment_entry.get() == "1.81"
        editor.pnc_enrichment_text.set("2.35")
        editor.apply_enrichment_entry()
        deadline = time.monotonic() + 10
        while (editor._pnc_after or editor.busy) and time.monotonic() < deadline:
            tk_window.update()
            time.sleep(.01)
        assert editor.session.config.pnc_enrichment_threshold == 2.35
        assert editor.session.masks[55].pnc_override is True
        editor.set_tool("Add")
        tk_window.update()
        assert editor.outline_controls.winfo_viewable()
        editor.points = [(45, 1), (50, 1), (50, 6), (45, 6)]
        editor.finish_outline()
        tk_window.update()
        assert len(editor.session.masks) == 4
        assert not editor.outline_controls.winfo_viewable()
        editor.cancel_outline()
        editor.show_advanced()
        tk_window.update()
        assert editor.advanced_window.winfo_viewable()
    finally:
        if editor._pnc_worker:
            editor._pnc_worker.join(timeout=5)
        if editor._pnc_after:
            editor.window.after_cancel(editor._pnc_after)
        editor.window.after_cancel(editor._poll_id)
        editor.window.destroy()
