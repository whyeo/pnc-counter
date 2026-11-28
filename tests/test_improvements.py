import json
from dataclasses import replace

import numpy as np
import pytest
import tifffile
from skimage.draw import disk

from nucleus_analysis import AnalysisConfig, ReviewSession, analyze
from nucleus_analysis.benchmark import add_reference, benchmark, image_digest, projection_digest
from nucleus_analysis.imaging import project_array, read_image
from nucleus_analysis.output import export_result
from nucleus_analysis.phenotype import marker_image, segmentation_config


def scene():
    dapi = np.zeros((100, 160), dtype=np.uint16)
    pnc = np.zeros_like(dapi)
    masks = []
    for y, x, size in [(20, 20, 35), (60, 105, 25)]:
        dapi[y:y + size, x:x + size] = 2000
        yy, xx = np.mgrid[y:y + size, x:x + size]
        masks.append(np.ravel_multi_index((yy.ravel(), xx.ravel()), dapi.shape))
    for center in [(30, 30), (42, 42), (6, 140)]:
        rr, cc = disk(center, 3, shape=dapi.shape)
        pnc[rr, cc] = 5000
    projections = project_array(np.stack([dapi, pnc]), "CYX", metadata={"pixel_size_um": {"x": 0.5, "y": 0.25}})
    config = AnalysisConfig(backend="watershed", pnc_mode="pixels", min_nucleus_area=400, max_nucleus_area=2000,
                            threshold_mode="global")
    return projections, config, masks


def review_scene():
    p, config, masks = scene()
    result = analyze(p, config, masks=masks, mask_ids=[11, 22])
    return ReviewSession(p, config, result.masks, result.full_stats), result


def verified_scene():
    session, result = review_scene()
    session.reviewer = "Synthetic test reviewer"
    session.mark(session.masks, reviewed=True)
    return session, result


def test_physical_bounds_and_anisotropic_area():
    p, config, masks = scene()
    config = replace(config, min_nucleus_area_um2=50, max_nucleus_area_um2=200)
    effective = segmentation_config(config, p.metadata)
    assert (effective.min_nucleus_area, effective.max_nucleus_area) == (400, 1600)
    result = analyze(p, config, masks=masks)
    assert result.full_stats[0]["Area_um2"] == 625 * 0.125
    calibrated = replace(config, pixel_size_x_um=0.1, pixel_size_y_um=0.1,
                         min_nucleus_area_um2=0.1, max_nucleus_area_um2=0.1)
    assert segmentation_config(calibrated, {}).max_nucleus_area == 10
    with pytest.raises(ValueError, match="calibrated pixel"):
        segmentation_config(config, {})


def test_physical_bounds_apply_before_automatic_segmentation():
    p, config, _ = scene()
    config = replace(config, min_nucleus_area_um2=100, max_nucleus_area_um2=200)
    result = analyze(p, config)
    assert result.basic_stats["n_total"] == 1  # only the larger nucleus exceeds 800 px


def test_ome_tiff_calibration(tmp_path):
    path = tmp_path / "calibrated.ome.tif"
    data = np.zeros((2, 20, 30), dtype=np.uint16)
    tifffile.imwrite(path, data, metadata={"axes": "CYX", "PhysicalSizeX": 200,
                       "PhysicalSizeXUnit": "nm", "PhysicalSizeY": 0.4, "PhysicalSizeYUnit": "µm"})
    assert read_image(path).metadata["pixel_size_um"] == {"x": 0.2, "y": 0.4}


def test_border_rule_preserves_geometry_and_changes_count():
    p, config, masks = scene()
    edge = np.ravel_multi_index(np.mgrid[10:20, 0:10].reshape(2, -1), p.dapi_max.shape)
    result = analyze(p, replace(config, border_policy="exclude"), masks=[*masks, edge])
    assert result.basic_stats["n_total"] == 2 and result.basic_stats["n_bad"] == 1
    assert len(result.masks) == 3
    assert sum(row["ExcludedByBorder"] for row in result.full_stats) == 1
    session = ReviewSession(p, result.config, result.masks, result.full_stats)
    assert session.counts()[0]["n_total"] == 2
    session.config = replace(config, border_policy="include")
    assert session.counts()[0]["n_total"] == 3


def test_spot_mode_counts_objects_and_preserves_pixel_measurement():
    p, config, masks = scene()
    config = replace(config, pnc_mode="spots", min_spot_count=2, spot_min_area=5, spot_max_area=100)
    result = analyze(p, config, masks=masks, mask_ids=[11, 22])
    assert result.basic_stats["n_positive"] == 1
    assert result.full_stats[0]["NumberPNCSpots"] == 2
    assert result.full_stats[0]["NumberCh2PixelsPositive"] == 50
    assert len(result.spots) == 3
    assert sum(spot["NucleusID"] == 0 for spot in result.spots) == 1
    assert result.images["pnc_spots"].dtype == np.uint32
    session = ReviewSession(p, config, result.masks, result.full_stats)
    assert session.counts()[0] == {**result.basic_stats, "n_flagged": 0}
    assert session.counts()[1][11]["spots"] == 2
    session.config = replace(config, min_spot_count=3)
    assert session.counts()[0]["n_positive"] == 0


def test_spot_size_noise_filter_and_unique_assignment():
    p, config, masks = scene()
    config = replace(config, pnc_mode="spots", spot_min_area=30)
    assert not analyze(p, config, masks).spots
    config = replace(config, spot_min_area=5, spot_max_area=100)
    # A contained duplicate is supplied explicitly to test unique spot ownership.
    smaller = masks[0][np.unravel_index(masks[0], p.dapi_max.shape)[0] < 37]
    result = analyze(p, config, masks=[masks[0], smaller], mask_ids=[11, 33], suppress_overlaps=False)
    assert sum(row["NumberPNCSpots"] for row in result.full_stats) == 2
    assert next(row for row in result.full_stats if row["MaskID"] == 33)["NumberPNCSpots"] == 1


def test_background_subtraction_is_explicit_and_spot_only():
    p, config, _ = scene()
    enabled = replace(config, spot_background_sigma=5)
    np.testing.assert_array_equal(marker_image(p.pnc_max, enabled), p.pnc_max)
    corrected = marker_image(p.pnc_max, replace(enabled, pnc_mode="spots"))
    assert corrected.dtype == p.pnc_max.dtype
    assert np.any(corrected != p.pnc_max) and np.all(corrected >= 0)


def test_spot_csv_and_visual_export(tmp_path):
    p, config, masks = scene()
    result = analyze(p, replace(config, pnc_mode="spots"), masks)
    export_result(result, tmp_path)
    assert (tmp_path / "spots.csv").read_text().count("\n") == 4
    assert "NumberPNCSpots" in (tmp_path / "nuclei.csv").read_text()


@pytest.mark.parametrize("changes", [{"pixel_size_x_um": 0.5}, {"min_nucleus_area_um2": 2},
                                    {"pixel_size_x_um": -1, "pixel_size_y_um": 1},
                                    {"border_margin": -1}, {"spot_min_area": 0},
                                    {"spot_min_area": 200, "spot_max_area": 10},
                                    {"spot_background_sigma": float("nan")}])
def test_new_settings_validate(changes):
    with pytest.raises(ValueError):
        AnalysisConfig(**changes)


def test_review_queue_confirmation_and_manual_calls_round_trip(tmp_path):
    session, _ = review_scene()
    assert len(session.review_queue("unreviewed")) == 2
    session.mark([22], flagged=True)
    assert session.review_queue("all")[0]["MaskID"] == 22
    session.reviewer = "Synthetic reviewer"
    session.mark([11], note="Two distinct bright puncta", pnc_override=False)
    assert session.counts()[0]["n_positive"] == 0
    assert session.result().basic_stats["n_positive"] == 0
    session.mark([11], reviewed=True)
    assert [r["MaskID"] for r in session.review_queue("unreviewed")] == [22]
    path, _ = session.save(tmp_path)
    reopened = ReviewSession.open(path)
    assert reopened.masks[11].reviewed
    assert reopened.masks[11].note == "Two distinct bright puncta"
    assert reopened.masks[11].reviewer == "Synthetic reviewer"
    assert reopened.masks[11].pnc_override is False
    reopened.redraw(11, [(20, 20), (53, 20), (53, 53), (20, 53)])
    assert not reopened.masks[11].reviewed and reopened.masks[11].pnc_override is None


def test_reference_gate_and_perfect_benchmark(tmp_path):
    session, result = review_scene()
    with pytest.raises(ValueError, match="reviewer name"):
        add_reference(session, tmp_path / "refs", split="test", group="specimen-A")
    session.reviewer = "Synthetic reviewer"
    with pytest.raises(ValueError, match="Confirm every"):
        add_reference(session, tmp_path / "refs", split="test", group="specimen-A")
    session.mark(session.masks, reviewed=True)
    manifest = add_reference(session, tmp_path / "refs", split="test", group="specimen-A")
    relative = json.loads(manifest.read_text())["cases"][0]["review_directory"]
    assert relative.startswith("reviews/") and "\\" not in relative
    export_result(result, tmp_path / "predictions")
    report = benchmark(manifest, tmp_path / "predictions")
    assert report["instance_f1"] == report["pnc_f1"] == 1
    assert report["nucleus_count_mae"] == report["positive_count_mae"] == 0
    assert report["percentage_mae_pp"] == 0
    assert image_digest(tmp_path / "predictions") == projection_digest(session.projections)


def test_benchmark_penalizes_missing_positive_nucleus(tmp_path):
    session, _ = verified_scene()
    manifest = add_reference(session, tmp_path / "refs", split="test", group="specimen-A")
    result = analyze(session.projections, session.config, masks=[session.masks[22].pixels])
    export_result(result, tmp_path / "predictions")
    report = benchmark(manifest, tmp_path / "predictions")
    assert report["instance_precision"] == 1
    assert report["instance_recall"] == 0.5
    assert report["instance_f1"] == pytest.approx(2 / 3)
    assert report["positive_count_mae"] == 1 and report["pnc_recall"] == 0
    assert report["percentage_mae_pp"] == 50


def test_reference_blocks_duplicate_images_and_group_leakage(tmp_path):
    session, _ = verified_scene()
    manifest = add_reference(session, tmp_path, split="test", group="specimen-A")
    before = list((tmp_path / "reviews").iterdir())
    with pytest.raises(ValueError, match="already registered"):
        add_reference(session, tmp_path, split="test", group="specimen-A")
    assert list((tmp_path / "reviews").iterdir()) == before
    with pytest.raises(ValueError, match="both validation and test"):
        add_reference(session, tmp_path, split="validation", group="specimen-A")
    document = json.loads(manifest.read_text())
    document["cases"].append({**document["cases"][0], "image_sha256": "different", "split": "validation"})
    manifest.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="group leakage"):
        benchmark(manifest, tmp_path / "predictions")


def test_benchmark_rejects_missing_ambiguous_or_changed_inputs(tmp_path):
    session, result = verified_scene()
    manifest = add_reference(session, tmp_path / "refs", split="test", group="A")
    with pytest.raises(ValueError, match="Missing prediction"):
        benchmark(manifest, tmp_path / "predictions")
    export_result(result, tmp_path / "predictions/one")
    export_result(result, tmp_path / "predictions/two")
    with pytest.raises(ValueError, match="Multiple predictions"):
        benchmark(manifest, tmp_path / "predictions")
    case = json.loads(manifest.read_text())["cases"][0]
    path = manifest.parent / case["review_directory"] / "review.json"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="changed after registration"):
        benchmark(manifest, tmp_path / "predictions/one")


def test_review_measurement_checksum(tmp_path):
    session, _ = review_scene()
    path, _ = session.save(tmp_path)
    with (path / "nuclei.csv").open("a") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="measurements checksum"):
        ReviewSession.open(path)


def test_benchmark_detects_wrong_calls_even_when_counts_match(tmp_path):
    session, _ = verified_scene()
    manifest = add_reference(session, tmp_path / "refs", split="test", group="synthetic-A")
    result = analyze(session.projections, session.config,
                     masks=[session.masks[11].pixels, session.masks[22].pixels], mask_ids=[11, 22],
                     positive_overrides={11: False, 22: True})
    export_result(result, tmp_path / "predictions")
    report = benchmark(manifest, tmp_path / "predictions")
    assert report["positive_count_mae"] == report["percentage_mae_pp"] == 0
    assert report["instance_f1"] == 1 and report["pnc_f1"] == 0
    assert report["cases"][0]["pnc_fp"] == report["cases"][0]["pnc_fn"] == 1


def test_empty_fields_require_confirmation_and_evaluate_without_nan(tmp_path):
    config = AnalysisConfig(backend="watershed")
    p = project_array(np.zeros((2, 20, 30), dtype=np.uint16), "CYX")
    result = analyze(p, config, masks=[])
    session = ReviewSession(p, config, [], [])
    session.reviewer = "Synthetic empty-field reviewer"
    with pytest.raises(ValueError, match="confirm the empty"):
        add_reference(session, tmp_path / "refs", split="test", group="empty-A")
    session.mark([], reviewed=True)
    assert session.empty_reviewed and session.dirty
    session.undo()
    assert not session.empty_reviewed
    session.redo()
    manifest = add_reference(session, tmp_path / "refs", split="test", group="empty-A")
    export_result(result, tmp_path / "predictions")
    report = benchmark(manifest, tmp_path / "predictions")
    assert report["nucleus_count_mae"] == 0
    assert report["percentage_mae_pp"] is None and report["instance_f1"] is None
    json.dumps(report, allow_nan=False)


def test_benchmark_refuses_different_border_protocols(tmp_path):
    session, _ = verified_scene()
    manifest = add_reference(session, tmp_path / "refs", split="test", group="A")
    result = analyze(session.projections, replace(session.config, border_policy="exclude"),
                     masks=[m.pixels for m in session.masks.values()])
    export_result(result, tmp_path / "predictions")
    with pytest.raises(ValueError, match="border rules differ"):
        benchmark(manifest, tmp_path / "predictions")


def test_touching_spots_are_split_and_large_diffuse_object_is_filtered():
    pnc = np.zeros((100, 160), dtype=np.uint16)
    for center in [(30, 30), (30, 38)]:
        rr, cc = disk(center, 5, shape=pnc.shape)
        pnc[rr, cc] = 5000
    rr, cc = disk((70, 120), 16, shape=pnc.shape)
    pnc[rr, cc] = 5000
    config = AnalysisConfig(backend="watershed", threshold_mode="global", pnc_mode="spots",
                            spot_min_area=5, spot_max_area=200)
    p = project_array(np.stack([np.zeros_like(pnc), pnc]), "CYX")
    result = analyze(p, config, masks=[])
    assert len(result.spots) == 2
    assert all(spot["NucleusID"] == 0 for spot in result.spots)


def test_confirming_a_flagged_detection_requires_resolving_the_flag():
    session, _ = review_scene()
    session.mark([11], flagged=True)
    with pytest.raises(ValueError, match="Resolve the follow-up"):
        session.mark([11], reviewed=True)
    assert session.masks[11].flagged and not session.masks[11].reviewed


def test_protocol_changes_require_reverification(tmp_path):
    session, _ = verified_scene()
    assert not session.review_queue("unreviewed")
    session.config = replace(session.config, positive_threshold=100)
    assert len(session.review_queue("unreviewed")) == 2
    with pytest.raises(ValueError, match="Confirm every"):
        add_reference(session, tmp_path, split="test", group="A")
