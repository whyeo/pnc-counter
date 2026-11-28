"""Desktop regressions exercise real selection callbacks and asynchronous batches."""

import hashlib
import subprocess
import sys
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile

from nucleus_analysis import AnalysisConfig
from nucleus_analysis.cli import run_batch
from nucleus_analysis.gui import CounterApp
from nucleus_analysis.preferences import (
    cached_hardware,
    load_preferences,
    runtime_signature,
    save_preferences,
)
from nucleus_analysis.projection_cache import read_cached
from nucleus_analysis.workflow import inspect_image, raw_preview, suggest_channels


def make_image(path, names=("DAPI", "PNC"), timepoints=1):
    image = np.zeros((timepoints, 2, 64, 64), dtype=np.uint16)
    image[:, 0, 10:30, 12:32] = 2000
    image[:, 1, 15:20, 18:22] = 5000
    if timepoints == 1:
        image, axes = image[0], "CYX"
    else:
        axes = "TCYX"
    tifffile.imwrite(path, image, ome=True, metadata={"axes": axes, "Channel": {"Name": names},
                         "PhysicalSizeX": .2, "PhysicalSizeY": .4})
    return path


def pump(root, predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    root.update()
    assert predicate(), "Desktop task did not finish"


@pytest.fixture
def app(tmp_path, tk_window):
    root = tk_window
    app = CounterApp(root, preference_file=tmp_path / "prefs.json", initialize=False)
    app.hardware = {"device": "cpu", "name": "Test CPU", "sam2_installed": False,
                    "runtime": runtime_signature()}
    yield app
    app.cancel.set()
    for token in root.tk.call("after", "info"):
        # Native ttk timer scripts are Tcl lists, not Python callback names.
        root.tk.call("after", "cancel", token)
    for thread in app.background_threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    root.destroy()


def test_large_main_buttons_remain_visible_at_minimum_window_size(app):
    root = app.root
    root.geometry("920x650")
    root.deiconify()
    root.update()
    left, top = root.winfo_rootx(), root.winfo_rooty()
    right, bottom = left + root.winfo_width(), top + root.winfo_height()
    for widget in [*(w for w, _ in app.controls), app.cancel_button]:
        assert widget.winfo_viewable(), widget.cget("text")
        assert widget.winfo_height() >= 32
        assert widget.winfo_rootx() >= left
        assert widget.winfo_rootx() + widget.winfo_width() <= right
        assert widget.winfo_rooty() + widget.winfo_height() <= bottom


def test_saved_profile_and_runtime_invalidation(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    hardware = {"device": "cuda", "name": "Test GPU", "runtime": runtime_signature()}
    save_preferences(path, {"hardware": hardware, "channel_mappings": {"acquisition": {"dapi_channel": 1}}})
    saved = load_preferences(path)
    assert cached_hardware(saved) == hardware
    monkeypatch.setattr("nucleus_analysis.preferences.runtime_signature", lambda: {"different": True})
    assert cached_hardware(saved) is None
    path.write_text("{broken")
    assert load_preferences(path) == {"schema": 1}


def test_metadata_channels_and_acquisition_signature(tmp_path):
    a = inspect_image(make_image(tmp_path / "a.ome.tif"))
    b = inspect_image(make_image(tmp_path / "b.ome.tif", names=("PNC", "DAPI")))
    c = inspect_image(make_image(tmp_path / "c.ome.tif", timepoints=2))
    assert suggest_channels(a) == ({"dapi_channel": 0, "pnc_channel": 1}, True)
    assert suggest_channels(b) == ({"dapi_channel": 1, "pnc_channel": 0}, True)
    assert len({m["signature"] for m in (a, b, c)}) == 3
    assert a["pixel_size_um"] == {"x": .2, "y": .4}
    assert not suggest_channels({"channels": ["DAPI", "TxRED"]})[1]
    assert raw_preview(tmp_path / "a.ome.tif", AnalysisConfig()).size == (600, 420)


def test_projection_cache_reuses_only_compatible_selection(tmp_path, monkeypatch):
    path = make_image(tmp_path / "source.ome.tif", timepoints=2)
    original = read_cached(path, AnalysisConfig(), cache=tmp_path / "cache")
    import nucleus_analysis.projection_cache as module
    real_read = module.read_image
    calls = []

    def read(*args, **kwargs):
        calls.append(args[1])
        return real_read(*args, **kwargs)
    monkeypatch.setattr(module, "read_image", read)
    repeated = read_cached(path, AnalysisConfig(positive_threshold=99), cache=tmp_path / "cache")
    assert not calls
    np.testing.assert_array_equal(original.pnc_max, repeated.pnc_max)
    read_cached(path, AnalysisConfig(time_index=1), cache=tmp_path / "cache")
    assert len(calls) == 1
    cached = list((tmp_path / "cache/projections").glob("*.npz"))
    for target in cached:
        target.write_bytes(b"broken")
    read_cached(path, AnalysisConfig(), cache=tmp_path / "cache")
    assert len(calls) == 2


def test_nd2_preview_owns_pixels_before_reader_closes(monkeypatch):
    import nd2

    frame = np.zeros((2, 64, 64), dtype=np.uint16)
    frame[:, 10:40, 10:40] = 5000

    class Reader:
        loop_indices = [{}]
        sizes = {"C": 2, "Y": 64, "X": 64}
        metadata = SimpleNamespace(channels=[])

        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            frame.fill(0)  # Model reader-owned pixels becoming unavailable.

        def read_frame(self, index):
            return frame

    monkeypatch.setattr(nd2, "ND2File", Reader)
    image = raw_preview("source.nd2", AnalysisConfig(), (200, 200))
    # Exclude the text labels: the actual image must still contain bright nuclei.
    assert np.asarray(image)[40:100].max() == 255


def test_preview_matches_selected_analysis_projection(tmp_path, monkeypatch):
    import nucleus_analysis.projection_cache as module
    from nucleus_analysis.imaging import read_image

    # The signal is absent from plane zero and present at the selected T/P/C.
    array = np.zeros((2, 2, 3, 2, 32, 32), dtype=np.uint16)
    array[1, 1, 2, 0, 8:20, 8:20] = 4000
    path = tmp_path / "selected.tif"
    tifffile.imwrite(path, array, metadata={"axes": "TPZCYX"})
    config = AnalysisConfig(dapi_channel=1, pnc_channel=0, time_index=1, position_index=1)
    expected = read_image(path, config)
    actual = []
    def cached(*args, **kwargs):
        result = read_image(*args, **{k: v for k, v in kwargs.items() if k != "cache"})
        actual.append(result)
        return result
    monkeypatch.setattr(module, "read_cached", cached)
    rendered = raw_preview(path, config, size=(200, 150), contrast=(0, 4000))
    np.testing.assert_array_equal(actual[0].pnc_max, expected.pnc_max)
    assert np.asarray(rendered)[30:, 100:].max() == 255
    assert expected.pnc_max.max() == 4000


def test_shared_display_contrast_does_not_change_measurements():
    from nucleus_analysis.imaging import display_uint8

    image = np.array([[100, 200], [300, 400]], dtype=np.uint16)
    saved = image.copy()
    a = display_uint8(image, (0, 1000))
    b = display_uint8(image + 100, (0, 1000))
    assert a[0, 1] == b[0, 0]
    np.testing.assert_array_equal(image, saved)


def test_batch_stages_and_repeated_threshold_analysis(tmp_path, monkeypatch):
    path = make_image(tmp_path / "source.ome.tif")
    config = AnalysisConfig(backend="watershed", min_nucleus_area=30, max_nucleus_area=2000)
    stages = []
    rows, errors = run_batch([path], config, tmp_path / "out", cache=tmp_path / "cache",
                             stage_progress=lambda p, s: stages.append((p, s)))
    assert not errors and len(rows) == 1
    assert [s for p, s in stages] == ["Loading image", "Finding nuclei", "Measuring PNC", "Saving results", "Done"]

    def unexpected(*_a, **_kw):
        raise AssertionError("Repeated measurement must reuse projections and masks")
    monkeypatch.setattr("nucleus_analysis.projection_cache.read_image", unexpected)
    monkeypatch.setattr("nucleus_analysis.segmentation.Segmenter.generate", unexpected)
    _, errors = run_batch([path], replace(config, positive_threshold=100), tmp_path / "out",
                          cache=tmp_path / "cache")
    assert not errors


def test_file_dialog_populates_rows_before_analysis(app, tmp_path, monkeypatch):
    first = make_image(tmp_path / "file with spaces.ome.tif")
    second = make_image(tmp_path / "second.ome.tif")
    monkeypatch.setattr("nucleus_analysis.gui.filedialog.askopenfilenames", lambda **kw: (str(first), str(second)))
    app.select_files()
    assert len(app.table.get_children()) == 2
    item = app.item_by_path[first]
    assert app.table.item(item, "values") == (first.name, "Ready", "", "", "")
    app.update_result(first, {"percentage": 50, "n_positive": 2, "n_total": 4}, tmp_path, None)
    assert app.item_by_path[first] == item and len(app.table.get_children()) == 2
    assert app.table.item(item, "values") == (first.name, "Done", "2", "4", "50.00%")
    app.update_result(second, None, None, "test failure")
    assert app.table.item(app.item_by_path[second], "values")[2:] == ("", "", "")


def test_drop_folder_and_files_deduplicates_and_excludes_results(app, tmp_path):
    folder = tmp_path / "folder with spaces"
    folder.mkdir()
    source = make_image(folder / "one.ome.tif")
    generated = folder / "results"
    generated.mkdir()
    (generated / "analysis.json").write_text("{}")
    make_image(generated / "reviewed_labels.tif")
    assert app.drop_enabled
    event = SimpleNamespace(data=f"{{{folder.as_posix()}}} {{{source.as_posix()}}}")
    assert app.drop_files(event) == "copy"
    pump(app.root, lambda: not app.preparing)
    assert app.paths == [source]
    app.drop_files(SimpleNamespace(data=f"{{{source.as_posix()}}}"))
    assert len(app.table.get_children()) == 1


def test_auto_device_preserves_scientific_settings(app):
    initial = app.get_config()
    app.hardware = {"device": "cuda", "name": "Test GPU"}
    actual = app.get_config()
    assert actual == replace(initial, device="cuda")
    app.device_choice.set("cpu")
    assert app.get_config().device == "cpu"


def test_missing_sam_opens_guided_setup_before_checkpoint_selection(app, tmp_path, monkeypatch):
    app.add_paths([make_image(tmp_path / "source.ome.tif")])
    app.checkpoint.set("")
    opened = []
    monkeypatch.setattr(app, "setup_sam", lambda: opened.append(True))
    monkeypatch.setattr("nucleus_analysis.gui.messagebox.showinfo", lambda *a: pytest.fail("Open setup directly"))
    app.start()
    assert opened == [True]


def test_real_channel_dialog_receives_background_preview(app, tmp_path):
    path = make_image(tmp_path / "channels.ome.tif", names=("DAPI", "TxRED"))
    loaded = []

    def accept_when_loaded():
        dialogs = [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)]
        if dialogs:
            dialog = dialogs[0]
            labels = [w for w in dialog.winfo_children() if isinstance(w, tk.ttk.Label)]
            if any(hasattr(w, "image") for w in labels):
                loaded.append(True)
                buttons = dialog.winfo_children()[-1]
                next(w for w in buttons.winfo_children() if w.cget("text") == "Use these channels").invoke()
                return
        app.root.after(20, accept_when_loaded)
    app.root.after(20, accept_when_loaded)
    chosen = app.channel_dialog(path, inspect_image(path))
    assert loaded and chosen == {"dapi_channel": 0, "pnc_channel": 1, "time_index": 0, "position_index": 0}


def test_advanced_save_and_cancel(app):
    def button(dialog, label):
        return next(w for w in dialog.winfo_children()[-1].winfo_children() if w.cget("text") == label)
    app.advanced_settings()
    dialog = next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))
    app.values["positive_threshold"].set("30")
    button(dialog, "Cancel").invoke()
    assert app.get_config().positive_threshold == 10
    app.advanced_settings()
    dialog = next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))
    app.values["positive_threshold"].set("30")
    button(dialog, "Save settings").invoke()
    assert load_preferences(app.preference_file)["analysis"]["positive_threshold"] == 30


def test_stopped_batch_retains_unprocessed_rows(app, tmp_path, monkeypatch):
    paths = [make_image(tmp_path / f"{i}.ome.tif") for i in range(2)]
    app.add_paths(paths)
    items = app.table.get_children()

    def batch(paths, config, output, **kwargs):
        kwargs["stage_progress"](paths[0], "Finding nuclei")
        kwargs["progress"](paths[0], {"percentage": 0, "n_positive": 0, "n_total": 1}, tmp_path, None)
        app.cancel.set()
    monkeypatch.setattr("nucleus_analysis.gui.run_batch", batch)
    config = app.get_config()
    app.launch_batch(paths, config, dict.fromkeys(paths, config))
    pump(app.root, lambda: app.status.get().startswith("Stopped:"))
    assert app.table.get_children() == items
    assert app.table.set(items[0], "total") == "1"
    assert app.table.item(items[1], "values") == (paths[1].name, "Not run", "", "", "")


def test_manual_acquisition_indices_are_respected(app, tmp_path, monkeypatch):
    path = make_image(tmp_path / "manual.ome.tif", timepoints=2)
    app.add_paths([path])
    app.values["dapi_channel"].set("1")
    app.values["pnc_channel"].set("0")
    app.values["time_index"].set("1")
    app.manual_channels.set(True)
    configs = []
    monkeypatch.setattr(app, "channel_dialog", lambda *a: pytest.fail("Manual override must not be replaced"))
    monkeypatch.setattr(app, "launch_batch", lambda paths, base, selected: configs.append(selected[path]))
    app.finish_prepare(([path], {path: inspect_image(path)}, [], True))
    assert configs[0].dapi_channel == 1 and configs[0].pnc_channel == 0 and configs[0].time_index == 1


def test_redetect_then_cached_launch_skips_probe(app, monkeypatch):
    profile = {"device": "cuda", "name": "New GPU", "runtime": runtime_signature()}
    calls = []
    monkeypatch.setattr("nucleus_analysis.gui.detect_hardware", lambda: calls.append(True) or profile)
    app.redetect_hardware()
    pump(app.root, lambda: not app.setup_busy)
    assert len(calls) == 1
    # A relaunch owns a fresh Tcl interpreter in a fresh process. Two Tk roots
    # in this process share event machinery and can fail to initialize on Windows.
    code = "\n".join([
        "import sys, tkinter as tk",
        "from unittest.mock import patch",
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / 'src')!r})",
        "from nucleus_analysis.gui import CounterApp",
        "root = tk.Tk(); root.withdraw()",
        "with patch('nucleus_analysis.gui.detect_hardware') as detect:",
        f"    second = CounterApp(root, preference_file={str(app.preference_file)!r})",
        "    root.after(150, root.quit)",
        "    root.mainloop()",
        "    assert second.hardware['name'] == 'New GPU'",
        "    assert not second.setup_busy",
        "    detect.assert_not_called()",
        "    assert 'torch' not in sys.modules",
        "root.destroy()",
    ])
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True, timeout=20)


def test_gui_batch_retains_rows_and_remembers_ambiguous_mapping(app, tmp_path, monkeypatch):
    sources = [make_image(tmp_path / f"{i}.ome.tif", names=("DAPI", "TxRED")) for i in range(2)]
    app.values["backend"].set("watershed")
    app.values["min_nucleus_area"].set("30")
    app.values["max_nucleus_area"].set("2000")
    app.output.set(str(tmp_path / "results"))
    calls = []
    monkeypatch.setattr(app, "channel_dialog", lambda *a: calls.append(a) or
                        {"dapi_channel": 0, "pnc_channel": 1, "time_index": 0, "position_index": 0})
    app.add_paths(sources)
    original_items = app.table.get_children()
    app.start()
    pump(app.root, lambda: app.status.get().startswith("Finished:"))
    assert len(calls) == 1 and app.table.get_children() == original_items
    assert all(app.table.set(item, "status") == "Done" for item in original_items)
    app.start()
    pump(app.root, lambda: app.status.get().startswith("Finished:"))
    assert len(calls) == 1


def test_close_waits_for_background_preview_and_stops_with_active_timer(app, monkeypatch):
    import threading

    release = threading.Event()
    destroyed = []
    monkeypatch.setattr(app.root, "destroy", lambda: destroyed.append(True))
    thread = app.start_background(lambda: release.wait(5))
    app.set_activity(True)
    try:
        app.close()
        assert app.closing and app.cancel.is_set()
        assert not destroyed
    finally:
        release.set()
        thread.join(timeout=5)
    pump(app.root, lambda: bool(destroyed))
    # Leave the native progressbar timer running to exercise fixture cleanup.


def test_download_checksum_failure_and_existing_file(tmp_path, monkeypatch):
    from io import BytesIO

    from nucleus_analysis import setup_model
    body = b"test checkpoint"
    expected = hashlib.sha256(body).hexdigest()
    monkeypatch.setitem(setup_model.CHECKSUMS, "tiny", expected)

    def response(*a, **kw):
        stream = BytesIO(body)
        stream.headers = {"Content-Length": str(len(body))}
        return stream
    monkeypatch.setattr(setup_model.urllib.request, "urlopen", response)
    target = tmp_path / "model.pt"
    setup_model.download_checkpoint("tiny", target, lambda text: None)
    assert target.read_bytes() == body
    monkeypatch.setattr(setup_model.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Already installed"))
    setup_model.download_checkpoint("tiny", target, lambda text: None)
    target.unlink()
    monkeypatch.setattr(setup_model.urllib.request, "urlopen", response)
    monkeypatch.setitem(setup_model.CHECKSUMS, "tiny", "incorrect")
    with pytest.raises(ValueError, match="checksum"):
        setup_model.download_checkpoint("tiny", target, lambda text: None)
    assert not target.exists()
