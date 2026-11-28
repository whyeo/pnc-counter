"""Adaptive detection and review/export consistency on controlled signals."""

from dataclasses import replace

import numpy as np
import pytest

from nucleus_analysis import AnalysisConfig, analyze
from nucleus_analysis.adaptive_pnc import (
    adaptive_foreground,
    prepare_adaptive,
    sensitivity_threshold,
)
from nucleus_analysis.imaging import project_array
from nucleus_analysis.output import export_result
from nucleus_analysis.review import ReviewSession


def scene():
    yy, xx = np.mgrid[:100, :180]
    rng = np.random.default_rng(22)
    pnc = 300 + .3*xx + rng.normal(0, 2, xx.shape)
    pnc += 90*np.exp(-((yy-50)**2+(xx-45)**2)/8)
    masks = [np.flatnonzero((yy-50)**2+(xx-x)**2 < 30**2) for x in (45, 130)]
    return pnc, masks


def test_background_noise_and_gain_invariance():
    image, masks = scene()
    features = prepare_adaptive(image, masks)
    changed = prepare_adaptive(7*image+2500, masks)
    np.testing.assert_allclose(features.score, changed.score, atol=1e-4)
    mask = adaptive_foreground(features, 50)
    assert mask[50, 45]
    assert not mask.ravel()[masks[1]].any()


def test_flat_images_hot_pixels_and_empty_geometry():
    image = np.full((80, 80), 100, dtype=np.uint16)
    mask = np.arange(image.size)
    assert not adaptive_foreground(prepare_adaptive(image, [mask]), 100).any()
    image[40, 40] = 5000
    assert not adaptive_foreground(prepare_adaptive(image, [mask]), 100).any()
    assert not adaptive_foreground(prepare_adaptive(image, []), 100).any()


@pytest.mark.parametrize("value", [-1, 101, float("nan"), float("inf"), True])
def test_invalid_sensitivity_rejected(value):
    with pytest.raises(ValueError, match="pnc_sensitivity"):
        AnalysisConfig(pnc_sensitivity=value)


def test_slider_direction_and_score_foreground_nesting():
    image, masks = scene()
    features = prepare_adaptive(image, masks)
    assert sensitivity_threshold(0) > sensitivity_threshold(50) > sensitivity_threshold(100)
    strict = adaptive_foreground(features, 0, max_area=image.size)
    sensitive = adaptive_foreground(features, 100, max_area=image.size)
    assert np.all(~strict | sensitive)


def test_geometry_changes_invalidate_scores_and_match_replayed_results():
    image, masks = scene()
    pnc = np.rint(image).astype(np.uint16)
    projections = project_array(np.stack([np.arange(pnc.size, dtype=np.uint16).reshape(pnc.shape), pnc]), "CYX")
    config = AnalysisConfig(backend="watershed", pnc_mode="adaptive")
    result = analyze(projections, config, masks=masks)
    session = ReviewSession(projections, config, result.masks, result.full_stats)
    prepared = session._adaptive_features
    session.mark([1], rejected=True)
    assert session.counts()[0]["n_positive"] == 0
    assert session._adaptive_features is not prepared
    assert session.result().basic_stats == session.counts()[0]
    session.undo()
    assert session.counts()[0]["n_positive"] == 1
    session.redraw(1, [(20, 20), (32, 20), (32, 35), (20, 35)])
    assert session.counts()[0]["n_positive"] == 0
    assert session.result().basic_stats == session.counts()[0]


def test_review_slider_reuses_features_and_saved_calls_match(tmp_path, monkeypatch):
    image, masks = scene()
    pnc = np.rint(image).astype(np.uint16)
    dapi = np.arange(pnc.size, dtype=np.uint16).reshape(pnc.shape)
    projections = project_array(np.stack([dapi, pnc]), "CYX")
    config = AnalysisConfig(backend="watershed", pnc_mode="adaptive", min_nucleus_area=100,
                            max_nucleus_area=10000)
    result = analyze(projections, config, masks=masks)
    session = ReviewSession(projections, config, result.masks, result.full_stats)
    assert session.counts()[0]["n_positive"] == 1
    prepared = session._adaptive_features
    def fail(*args, **kwargs):
        pytest.fail("Sensitivity changes must reuse prepared geometry/image features")
    monkeypatch.setattr("nucleus_analysis.review.prepare_adaptive", fail)
    session.mark([2], pnc_override=True)
    session.set_pnc_config(replace(config, pnc_sensitivity=80))
    counts, _ = session.counts()
    assert session._adaptive_features is prepared
    assert counts["n_positive"] == 2
    assert session.undo()
    assert session.config == config and session.masks[2].pnc_override is True
    directory, saved = session.save(tmp_path)
    monkeypatch.undo()
    reopened = ReviewSession.open(directory)
    assert reopened.counts()[0] == saved
    assert reopened.config.pnc_mode == "adaptive" and reopened.masks[2].pnc_override is True
    assert "pnc_score" in np.load(directory / "images.npz", allow_pickle=False).files
    assert (directory / "spots.csv").is_file()
    export_result(result, tmp_path / "original")
    assert "PNCSignalScore" in (tmp_path / "original/nuclei.csv").read_text()


@pytest.mark.parametrize("label, mode", [("Background-aware (preview)", "adaptive"),
                                         ("Multiscale prominence (preview)", "prominence")])
def test_desktop_slider_latest_request_and_revision_without_sam(tk_window, tmp_path, monkeypatch, label, mode):
    import time

    from nucleus_analysis import review
    from nucleus_analysis.editor import ReviewEditor

    image, masks = scene()
    pnc = np.rint(image).astype(np.uint16)
    projections = project_array(np.stack([np.arange(pnc.size, dtype=np.uint16).reshape(pnc.shape), pnc]), "CYX")
    result = analyze(projections, AnalysisConfig(backend="watershed"), masks=masks)
    export_result(result, tmp_path / "analysis")
    chosen = []
    editor = ReviewEditor(tk_window, tmp_path / "analysis", on_protocol=chosen.append)
    builds = []
    original = getattr(review, "prepare_" + ("adaptive" if mode == "adaptive" else "prominence"))
    def slow(*args, **kwargs):
        builds.append(True)
        time.sleep(.20)
        return original(*args, **kwargs)
    monkeypatch.setattr(review, "prepare_" + ("adaptive" if mode == "adaptive" else "prominence"), slow)
    monkeypatch.setattr("nucleus_analysis.segmentation.Segmenter.generate",
                        lambda *a: pytest.fail("Slider/save must not rerun SAM"))

    def pump(condition):
        deadline = time.monotonic()+10
        while not condition() and time.monotonic() < deadline:
            tk_window.update()
            time.sleep(.01)
        assert condition()
    try:
        editor.pnc_method.set(label)
        editor.pnc_sensitivity.set(0)
        editor.schedule_pnc_preview()
        pump(lambda: editor.busy)
        editor.pnc_sensitivity.set(100)
        editor.schedule_pnc_preview()
        pump(lambda: not editor.busy and editor.session.config.pnc_mode == mode
             and editor.session.config.pnc_sensitivity == 100)
        assert len(builds) == 1
        editor.use_pnc_protocol()
        assert chosen[0].pnc_sensitivity == 100
        before = editor.session.counts()[0]
        editor.save_to(tmp_path / "reviews")
        pump(lambda: not editor.busy and editor.directory != (tmp_path / "analysis").resolve())
        assert ReviewSession.open(editor.directory).counts()[0] == before
    finally:
        if editor._pnc_worker:
            editor._pnc_worker.join(timeout=5)
        if editor._pnc_after:
            editor.window.after_cancel(editor._pnc_after)
        editor.window.after_cancel(editor._poll_id)
        editor.window.destroy()
