"""Behavioral regressions for the dev3 research prototype, not biological truth."""

import json

import numpy as np
import pytest

from nucleus_analysis.control_profile import compatible_floor, fit_profiles
from nucleus_analysis.enrichment_pnc import prepare_enrichment, select_enrichment
from nucleus_analysis.intensity_mixture import fit_intensity_mixture


def scene():
    yy, xx = np.mgrid[:81, :91]
    image = 200 + .15*xx + np.random.default_rng(8).normal(0, .5, xx.shape)
    image += 70*np.exp(-((yy-40)**2+(xx-45)**2)/6)
    return image, [np.flatnonzero((yy-40)**2+(xx-45)**2 < 30**2)]


def test_growth_measures_faint_surroundings_and_keeps_all_signal_dimensions():
    image, masks = scene()
    half = prepare_enrichment(image, masks, support="half")
    growth = prepare_enrichment(image, masks, support="growth")
    def near(rows):
        return min((r for r in rows if r["CandidateStatus"] == "measured"),
                   key=lambda r: (r["CentroidX"]-46)**2+(r["CentroidY"]-41)**2)
    h, g = near(half.candidates), near(growth.candidates)
    assert g["Area"] > h["Area"]
    assert g["SignedIntegratedExcess"] > h["SignedIntegratedExcess"]
    assert all(k in g for k in ("LocalContrast", "NuclearContrast", "RawSupportPixels", "LargestPixelFraction"))
    assert select_enrichment(growth, 100)[0][40, 45]


def test_flat_weak_noise_and_gain_and_single_hot_pixel_diagnostics():
    flat = np.full((65, 65), 100.)
    masks = [np.arange(flat.size)]
    assert not select_enrichment(prepare_enrichment(flat, masks), 100)[0].any()
    weak = flat + np.random.default_rng(1).normal(0, 1e-4, flat.shape)
    f = prepare_enrichment(weak, masks)
    assert not select_enrichment(f, 100)[0].any()
    assert any(r["CandidateStatus"].startswith("discarded") for r in f.candidates)
    image, masks = scene()
    a, b = prepare_enrichment(image, masks), prepare_enrichment(image*4, masks)
    np.testing.assert_array_equal(a.labels, b.labels)
    np.testing.assert_allclose(a.score, b.score, atol=1e-6)
    flat[32, 32] = 5000
    hot = prepare_enrichment(flat, [np.arange(flat.size)])
    assert any("possible hot pixel" in r["ReviewFlags"] for r in hot.candidates)
    # The research protocol records the hazard instead of hiding a zeroed signal.
    assert max(r["SignalScore"] for r in hot.candidates) > 0


def test_cached_selection_is_monotonic_and_z_is_supporting_only():
    image, masks = scene()
    a = prepare_enrichment(image, masks)
    evidence = {"score": np.full(image.shape, .001), "plane": np.full(image.shape, 5, dtype=int)}
    b = prepare_enrichment(image, masks, evidence=evidence)
    np.testing.assert_array_equal(a.score, b.score)
    previous = np.zeros(image.shape, bool)
    geometry = b.labels.copy()
    for sensitivity in np.linspace(0, 100, 21):
        current = select_enrichment(b, sensitivity)[0]
        assert np.all(~previous | current)
        previous = current
    np.testing.assert_array_equal(geometry, b.labels)
    assert any(c.get("BestZ") == 5 for c in b.candidates)
    json.dumps(b.candidates, allow_nan=False)


def test_mixture_unimodal_and_nonconvergence_fallbacks_do_not_force_a_call():
    constant = fit_intensity_mixture(np.full(100, 5.))
    assert constant["threshold"] is None
    noise = np.random.default_rng(6).normal(100, 3, 3000)
    single = fit_intensity_mixture(noise)
    assert single["threshold"] is None
    failed = fit_intensity_mixture(noise, max_iterations=1)
    assert failed["status"] == "nonconvergence" and failed["threshold"] is None
    tiny_tail = np.r_[np.random.default_rng(3).normal(100, 1, 970), np.full(30, 120.)]
    fitted = fit_intensity_mixture(tiny_tail)
    assert fitted["status"] == "two_components_diagnostic"
    assert 100 < fitted["threshold"] < 120
    json.dumps(fitted, allow_nan=False)


def test_optional_profile_is_development_only_and_protocol_and_acquisition_specific():
    protocol = {"method": "enrichment-v1", "support": "growth"}
    controls = [{"split": "development", "role": "negative_control", "field": str(i),
                 "source_sha256": str(i)*64, "acquisition_signature": "matching",
                 "automatic_nucleus_maxima": [0., .1, .2]} for i in (1, 2)]
    profile = fit_profiles(controls, protocol)
    floor, status = compatible_floor(profile, "matching", protocol)
    assert floor > 0 and status.startswith("compatible")
    assert compatible_floor(profile, "other-exposure", protocol)[0] is None
    assert compatible_floor(profile, "matching", {"method": "changed"})[0] is None
    sparse = fit_profiles(controls[:1], protocol)
    assert compatible_floor(sparse, "matching", protocol)[0] is None
    with pytest.raises(ValueError, match="development"):
        fit_profiles([{**controls[0], "split": "validation"}], protocol)
    image, masks = scene()
    f = prepare_enrichment(image, masks)
    plain = select_enrichment(f, 100)[0]
    calibrated = select_enrichment(f, 100, calibrated_floor=1e6)[0]
    assert plain.any() and not calibrated.any()
