"""Local fold units, eligibility, cached decisions and stored-protocol compatibility."""
import json
from dataclasses import replace

import numpy as np
import pytest

from nucleus_analysis.adaptive_pnc import AdaptiveFeatures
from nucleus_analysis.config import AnalysisConfig
from nucleus_analysis.local_enrichment import prepare_local_enrichment, select_local_enrichment


def fixed_proposal(monkeypatch, center=(25, 25), shape=(51, 51)):
    labels = np.zeros(shape, np.uint32)
    y, x = center
    labels[max(0, y-1):y+2, max(0, x-1):x+2] = 1
    row = {"SpotID": 1, "NucleusID": 7, "SignalScore": 9., "Area": int((labels > 0).sum()),
           "SeedY": y, "SeedX": x, "CandidateStatus": "measured", "RawSupportPixels": 9,
           "AnchorPixel": y*shape[1]+x, "CentroidX": x+1, "CentroidY": y+1}
    features = AdaptiveFeatures(np.zeros(shape), {}, labels, (row,))
    monkeypatch.setattr("nucleus_analysis.local_enrichment.prepare_enrichment", lambda *a, **kw: features)
    return labels


def test_raw_ratio_units_inclusive_cutoff_and_fixed_geometry(monkeypatch):
    geometry = fixed_proposal(monkeypatch)
    image = np.full((51, 51), 100, np.uint16)
    image[24:27, 24:27] = 200
    f = prepare_local_enrichment(image, [np.arange(image.size)], [7])
    assert f.candidates[0]["LocalEnrichment"] == 2.
    assert f.candidates[0]["LocalReferenceMedian"] == 100.
    assert f.measurements[7]["max_score"] == 2.
    assert select_local_enrichment(f, 2.)[0].sum() == 9
    assert not select_local_enrichment(f, 2.01)[0].any()
    np.testing.assert_array_equal(f.labels, geometry)
    assert f.candidates[0]["ProposalScore"] == 9.
    json.dumps(f.candidates, allow_nan=False)


def test_raw_median_does_not_turn_single_hot_pixel_into_enrichment(monkeypatch):
    fixed_proposal(monkeypatch)
    image = np.full((51, 51), 100, np.uint16)
    image[25, 25] = 60000
    f = prepare_local_enrichment(image, [np.arange(image.size)], [7])
    assert f.candidates[0]["Raw3x3Peak"] == 60000
    assert f.candidates[0]["LocalEnrichment"] == 1.
    assert not select_local_enrichment(f, 1.8)[0].any()


def test_missing_reference_flagged_without_inventing_ratio(monkeypatch):
    fixed_proposal(monkeypatch)
    image = np.full((51, 51), 100, np.uint16)
    pixels = np.flatnonzero(np.pad(np.ones((5, 5), bool), 23))
    f = prepare_local_enrichment(image, [pixels], [7])
    assert f.candidates[0]["LocalEnrichment"] is None
    assert not f.candidates[0]["EnrichmentEligible"]
    assert f.measurements[7]["status"] == "unsupported"
    assert "insufficient local reference" in f.measurements[7]["flags"]
    json.dumps(f.candidates, allow_nan=False)


def test_one_sided_reference_warns_without_changing_threshold_rule(monkeypatch):
    fixed_proposal(monkeypatch, center=(1, 1))
    image = np.full((51, 51), 100, np.uint16)
    image[:3, :3] = 250
    f = prepare_local_enrichment(image, [np.arange(image.size)], [7])
    assert f.candidates[0]["EnrichmentEligible"]
    assert "one-sided reference" in f.candidates[0]["ReviewFlags"]
    assert select_local_enrichment(f, 1.8)[0].any()


def test_new_default_and_imported_old_protocol_are_distinct(tmp_path):
    assert AnalysisConfig().pnc_mode == "enrichment"
    assert AnalysisConfig().pnc_enrichment_threshold == 1.8
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"backend": "watershed", "positive_threshold": 10}))
    assert AnalysisConfig.load(old).pnc_mode == "pixels"
    assert AnalysisConfig.from_dict({"pnc_enrichment_threshold": 2.1}).pnc_mode == "enrichment"
    current = tmp_path / "current.json"
    replace(AnalysisConfig(), pnc_enrichment_threshold=2.25).save(current)
    loaded = AnalysisConfig.load(current)
    assert loaded.pnc_mode == "enrichment" and loaded.pnc_enrichment_threshold == 2.25


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_fold_threshold_rejected(value):
    with pytest.raises(ValueError, match="pnc_enrichment_threshold"):
        AnalysisConfig(pnc_enrichment_threshold=value)


def test_review_threshold_cache_manual_override_and_revision(monkeypatch, tmp_path):
    from nucleus_analysis import ReviewSession, analyze
    from nucleus_analysis.imaging import Projections
    from nucleus_analysis.output import export_result

    y, x = np.mgrid[:101, :101]
    image = np.round(200 + 700*np.exp(-((x-50)**2+(y-50)**2)/18)).astype(np.uint16)
    dapi = np.full(image.shape, 100, np.uint8)
    projections = Projections(dapi.astype(float), dapi, image,
                              {"pixel_size_um": {"x": .1, "y": .1}})
    mask = np.flatnonzero((x-50)**2+(y-50)**2 < 30**2)
    config = AnalysisConfig(backend="watershed", min_nucleus_area=100, max_nucleus_area=20000)
    result = analyze(projections, config, [mask])
    assert result.basic_stats["n_positive"] == 1
    assert result.full_stats[0]["PNCEnrichment"] > 1.8
    original = tmp_path/"original"
    export_result(result, original)
    hashes = {p.name: p.read_bytes() for p in original.iterdir()}
    session = ReviewSession.open(original)
    assert "PNC measurement near cutoff" not in session.review_queue("all")[0]["reasons"]
    prepared = session._adaptive_features
    monkeypatch.setattr("nucleus_analysis.review.prepare_local_enrichment",
                        lambda *a, **k: pytest.fail("Threshold update prepared candidates again"))
    session.set_pnc_config(replace(config, pnc_enrichment_threshold=20.))
    assert session.counts()[0]["n_positive"] == 0
    assert session._adaptive_features is prepared
    session.mark([1], pnc_override=True)
    assert session.counts()[0]["n_positive"] == 1
    revision, counts = session.save(tmp_path/"revisions")
    monkeypatch.undo()
    reopened = ReviewSession.open(revision)
    assert reopened.config.pnc_enrichment_threshold == 20.
    assert reopened.masks[1].pnc_override is True
    assert reopened.counts()[0] == counts
    metadata = json.loads((revision/"analysis.json").read_text())
    assert metadata["pnc_detection"]["algorithm"] == "raw-3x3-median-local-ring-v1"
    from nucleus_analysis import __version__

    assert metadata["version"] == __version__
    assert all((original/name).read_bytes() == data for name, data in hashes.items())


def test_cli_exposes_fold_threshold():
    from nucleus_analysis.cli import build_parser

    args = build_parser().parse_args(["--pnc-mode", "enrichment", "--pnc-enrichment-threshold", "2.25"])
    assert args.pnc_mode == "enrichment" and args.pnc_enrichment_threshold == 2.25
