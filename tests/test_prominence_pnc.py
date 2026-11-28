"""Regression evidence for the experimental protocol, not biological accuracy."""

import json
from dataclasses import replace

import numpy as np
import pytest

from nucleus_analysis import AnalysisConfig, analyze
from nucleus_analysis.imaging import project_array
from nucleus_analysis.output import export_result
from nucleus_analysis.pnc_evidence import PlaneEvidence, evidence_metadata
from nucleus_analysis.prominence_pnc import prepare_prominence, select_prominence
from nucleus_analysis.review import ReviewSession


def scene(spacing=.15):
    yy, xx = np.mgrid[:80, :100]
    image = 200 + .1 * xx + np.random.default_rng(4).normal(0, .6, xx.shape)
    image += 120 * np.exp(-((yy-40)**2 + (xx-40)**2) / 4)
    mask = np.flatnonzero((yy-40)**2 + (xx-45)**2 < 29**2)
    return image, [mask], (spacing, spacing)


@pytest.mark.parametrize("kind", ["constant", "weak_noise", "gradient", "hot_pixel", "diffuse"])
def test_no_spot_from_unsupported_signal(kind):
    yy, xx = np.mgrid[:80, :80]
    image = np.full(xx.shape, 200., dtype=float)
    if kind == "weak_noise":
        image += np.random.default_rng(5).normal(0, .001, image.shape)
    if kind == "gradient":
        image += .3 * xx
    if kind == "hot_pixel":
        image[40, 40] = 5000
    if kind == "diffuse":
        image += 15 * np.exp(-((yy-40)**2+(xx-40)**2)/300)
    features = prepare_prominence(image, [np.arange(image.size)])
    assert not select_prominence(features, 100)[0].any()


@pytest.mark.parametrize("spacing", [.08, .15, .3, None])
def test_small_punctum_gain_and_offset(spacing):
    image, masks, calibration = scene(spacing)
    calibration = None if spacing is None else calibration
    original = prepare_prominence(image, masks, calibration=calibration)
    changed = prepare_prominence(image * 4 + 50, masks, calibration=calibration)
    assert select_prominence(original, 100)[0][40, 40]
    assert select_prominence(changed, 100)[0][40, 40]
    if calibration is None:
        assert "uncertain scale" in original.candidates[0]["ReviewFlags"]


def test_fixed_touching_geometry_monotonic_and_boundary_flags():
    image, masks, calibration = scene()
    yy, xx = np.mgrid[:80, :100]
    image += 100 * np.exp(-((yy-40)**2 + (xx-46)**2)/4)
    features = prepare_prominence(image, masks, calibration=calibration)
    assert len(features.candidates) >= 2
    previous = np.zeros(image.shape, bool)
    labels = features.labels.copy()
    for sensitivity in np.linspace(0, 100, 21):
        current = select_prominence(features, sensitivity)[0]
        assert np.all(~previous | current)
        previous = current
    np.testing.assert_array_equal(features.labels, labels)


def test_z_support_rejects_projected_pixel_mosaic_without_multislice_gate():
    yy, xx = np.mgrid[:70, :70]
    planes = np.full((9, 70, 70), 100., dtype=float)
    punctum = 100 * np.exp(-((yy-35)**2+(xx-25)**2)/4)
    planes[4] += punctum  # One focused plane must suffice, even at coarse spacing.
    for z, (y, x) in enumerate(np.ndindex(3, 3)):
        planes[z, y+34, x+44] += 100
    builder = PlaneEvidence()
    for z, plane in enumerate(planes):
        builder.add(plane, z)
    maximum = planes.max(axis=0)
    masks = [np.flatnonzero((yy-35)**2+(xx-x)**2 < 14**2) for x in (25, 45)]
    features = prepare_prominence(maximum, masks, evidence=builder.finish())
    foreground = select_prominence(features, 100)[0]
    assert foreground[35, 25]
    assert not foreground[34:37, 44:47].any()
    clear = next(c for c in features.candidates if c["NucleusID"] == 1)
    assert clear["BestZ"] == 4 and clear["ZFocusFraction"] == 1


def test_z_roundtrip_cache_geometry_and_manual_provenance(tmp_path, monkeypatch):
    image, masks, _ = scene()
    planes = np.stack([np.full_like(image, 200), image, np.full_like(image, 200)])
    config = AnalysisConfig(backend="watershed", pnc_mode="prominence", pnc_sensitivity=100)
    data = np.stack([np.broadcast_to(np.arange(image.size).reshape(image.shape), planes.shape), planes], axis=1)
    p = project_array(data, "ZCYX", config, {"z_spacing_um": 2.})
    assert p.metadata["pnc_evidence"]["z_spacing_um"] == 2.
    result = analyze(p, config, masks=masks)
    export_result(result, tmp_path / "original")
    session = ReviewSession.open(tmp_path / "original")
    assert session.counts()[0]["n_positive"] == 1
    features = session._adaptive_features
    def fail(*a, **kw):
        pytest.fail("Slider must reuse measurements and must not load SAM")
    monkeypatch.setattr("nucleus_analysis.review.prepare_prominence", fail)
    monkeypatch.setattr("nucleus_analysis.segmentation.Segmenter.generate", fail)
    session.set_pnc_config(replace(config, pnc_sensitivity=0))
    assert session.counts()[0]["n_positive"] == 0
    assert session._adaptive_features is features
    session.mark([1], pnc_override=True)
    directory, counts = session.save(tmp_path / "revisions")
    monkeypatch.undo()
    reopened = ReviewSession.open(directory)
    assert reopened.counts()[0] == counts
    row = reopened.result().full_stats[0]
    assert row["ManualPNCOverride"] == 1 and row["AutomaticPositive"] == 0
    info = json.loads((directory / "analysis.json").read_text())["pnc_detection"]
    assert info["evidence"]["schema"] == 1
    assert (directory / "pnc_candidates.csv").is_file()
    reopened.mark([1], rejected=True)
    assert reopened.counts()[0]["n_total"] == 0
    assert reopened._adaptive_features is not features


def test_2d_fallback_and_invalid_evidence():
    image, masks, _ = scene()
    features = prepare_prominence(image, masks)
    assert "2D fallback" in features.candidates[0]["ReviewFlags"]
    p = project_array(np.stack([image, image]), "CYX")
    p.pnc_evidence = {"score": np.ones(image.shape), "plane": np.ones(image.shape, dtype=int)}
    p.metadata["pnc_evidence"] = evidence_metadata(1)
    with pytest.raises(ValueError, match="plane indices"):
        p.__post_init__()


def test_evidence_cache_selection_algorithm_and_scale_invalidation(tmp_path, monkeypatch):
    import tifffile

    import nucleus_analysis.pnc_evidence as evidence
    import nucleus_analysis.projection_cache as cache

    image, _, _ = scene()
    path = tmp_path / "source.tif"
    array = np.stack([np.stack([image, image])] * 3).astype(np.uint16)
    tifffile.imwrite(path, array, metadata={"axes": "ZCYX"})
    config = AnalysisConfig(pnc_mode="prominence")
    cache.read_cached(path, config, cache=tmp_path / "cache")
    calls = []
    original = cache.read_image
    def read(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(cache, "read_image", read)
    repeated = cache.read_cached(path, replace(config, pnc_sensitivity=100), cache=tmp_path / "cache")
    assert not calls and repeated.pnc_evidence
    cache.read_cached(path, replace(config, pnc_z_policy="projection"), cache=tmp_path / "cache")
    cache.read_cached(path, replace(config, dapi_channel=1, pnc_channel=0), cache=tmp_path / "cache")
    cache.read_cached(path, replace(config, pixel_size_x_um=.2, pixel_size_y_um=.3), cache=tmp_path / "cache")
    assert len(calls) == 3
    with pytest.raises(ValueError, match="different pixel scale"):
        evidence.selected_evidence(repeated, replace(config, pixel_size_x_um=.1, pixel_size_y_um=.1))
    monkeypatch.setattr(cache, "ALGORITHM", "test-new-evidence-algorithm")
    cache.read_cached(path, config, cache=tmp_path / "cache")
    assert len(calls) == 4


def test_gui_load_and_inspect_z_never_changes_calls_or_runs_sam(tk_window, tmp_path, monkeypatch):
    import time

    import tifffile

    from nucleus_analysis.editor import ReviewEditor
    from nucleus_analysis.imaging import read_image

    image, masks, _ = scene()
    stack = np.stack([np.full_like(image, 200), image, np.full_like(image, 200)])
    data = np.stack([np.broadcast_to(np.arange(image.size).reshape(image.shape), stack.shape), stack], axis=1).astype(np.uint16)
    path = tmp_path / "source.tif"
    tifffile.imwrite(path, data, metadata={"axes": "ZCYX"})
    config = AnalysisConfig(backend="watershed")
    p = read_image(path, config)
    export_result(analyze(p, config, masks=masks), tmp_path / "original")
    editor = ReviewEditor(tk_window, tmp_path / "original")
    monkeypatch.setattr("nucleus_analysis.segmentation.Segmenter.generate",
                        lambda *a: pytest.fail("Remeasurement must not call SAM"))
    def pump(condition):
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline:
            tk_window.update()
            time.sleep(.01)
        assert condition()
    try:
        editor.load_z_evidence()
        pump(lambda: not editor.busy and editor.session.config.pnc_mode == "prominence")
        assert editor.session.projections.pnc_evidence
        before = editor.session.counts()[0]
        editor.selected = {1}
        editor.inspect_z_plane()
        pump(lambda: not editor.busy and editor.inspection_plane is not None)
        assert editor.inspection_z == 1
        assert editor.session.counts()[0] == before
        editor.return_projection()
        assert editor.inspection_plane is None and editor.session.counts()[0] == before
    finally:
        if editor._pnc_worker:
            editor._pnc_worker.join(timeout=5)
        editor.window.after_cancel(editor._poll_id)
        editor.window.destroy()
