"""Ensure diagnostic instrumentation reproduces dev2 and exposes discarded seeds."""

import numpy as np

from nucleus_analysis.prominence_pnc import prepare_prominence
from tools.pnc_loss_audit import ABLATIONS, instrumented


def test_loss_instrumentation_has_exact_baseline_parity():
    yy, xx = np.mgrid[:60, :70]
    image = 200. + .2 * xx + np.random.default_rng(2).normal(0, 1, xx.shape)
    image += 100 * np.exp(-((yy-30)**2+(xx-35)**2)/6)
    masks = [np.flatnonzero((yy-30)**2+(xx-35)**2 < 25**2)]
    baseline = prepare_prominence(image, masks)
    measured, discarded = instrumented()(image, masks)
    np.testing.assert_array_equal(baseline.labels, measured.labels)
    np.testing.assert_array_equal(baseline.score, measured.score)
    assert len(measured.candidates) == len(baseline.candidates)
    for before, after in zip(baseline.candidates, measured.candidates):
        assert all(after[k] == v for k, v in before.items())
        assert after["PreGateScore"] >= after["PrePenaltyScore"]
    assert isinstance(discarded, list)


def test_every_declared_one_factor_ablation_runs_and_is_finite():
    yy, xx = np.mgrid[:50, :50]
    image = 100. + 90 * np.exp(-((yy-25)**2+(xx-25)**2)/5)
    masks = [np.arange(image.size)]
    for name in ABLATIONS:
        measured, discarded = instrumented(name)(image, masks)
        assert np.isfinite(measured.score).all()
        assert all(r["Stage"] == "discarded: raw anchor absent" for r in discarded)


def test_raw_support_can_discard_a_peak_before_the_slider_sees_it():
    image = np.full((60, 60), 100., dtype=float)
    image[28:33, 28:33] += 100
    image[30, 30] = 100
    masks = [np.arange(image.size)]
    _, discarded = instrumented()(image, masks, calibration=(.05, .05))
    # A ring-like focus can have a smoothed maximum on a low raw pixel.
    assert discarded
    assert any(d["PeakSNR"] > 2 for d in discarded)
    _, alternative = instrumented("support_no_raw")(image, masks, calibration=(.05, .05))
    assert len(alternative) < len(discarded)
