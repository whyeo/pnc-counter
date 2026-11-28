import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage as ndi
from scipy.io import savemat
from skimage.draw import disk

from nucleus_analysis import AnalysisConfig, analyze, count_pnc
from nucleus_analysis.cli import main, run_batch
from nucleus_analysis.evaluation import compare_labels
from nucleus_analysis.imaging import project_array, scale_uint8
from nucleus_analysis.morphology import corrected_perimeter
from nucleus_analysis.output import export_result
from nucleus_analysis.pipeline import threshold_pnc
from nucleus_analysis.quality import load_legacy_svm, svm_decision
from nucleus_analysis.segmentation import (
    Segmenter,
    _rle_indices,
    cache_fingerprint,
    load_masks,
    save_masks,
)


def synthetic_image():
    dapi = np.zeros((180, 240), dtype=np.uint16)
    pnc = np.zeros_like(dapi)
    masks = []
    for center in [(55, 55), (120, 170)]:
        rr, cc = disk(center, 25, shape=dapi.shape)
        dapi[rr, cc] = 1000
        masks.append(np.ravel_multi_index((rr, cc), dapi.shape))
    pnc.ravel()[masks[0][:12]] = 5000
    projections = project_array(np.stack([dapi, pnc]), "CYX")
    config = AnalysisConfig(backend="watershed", pnc_mode="pixels", min_nucleus_area=500,
                            max_nucleus_area=5000, threshold_mode="global", positive_threshold=10)
    return projections, masks, config


def test_positive_pixel_boundary_and_coordinates():
    projections, masks, config = synthetic_image()
    result = analyze(projections, config, masks=masks)
    assert result.basic_stats == dict(percentage=50, n_positive=1, n_negative=1,
                                      n_total=2, n_masks=2, n_bad=0)
    assert result.full_stats[0]["NumberCh2PixelsPositive"] == 12
    assert result.full_stats[0]["CentroidX"] == 56
    assert result.full_stats[0]["CentroidY"] == 56
    assert analyze(projections, replace(config, positive_threshold=12), masks).basic_stats["n_positive"] == 1
    assert analyze(projections, replace(config, positive_threshold=13), masks).basic_stats["n_positive"] == 0


def test_duplicate_overlap_removed():
    projections, masks, config = synthetic_image()
    result = analyze(projections, config, masks=[*masks, masks[0]])
    assert result.basic_stats["n_total"] == 2


def test_empty_images_and_no_masks_are_finite():
    array = np.zeros((2, 50, 60), dtype=np.uint16)
    projections = project_array(array, "CYX")
    result = analyze(projections, AnalysisConfig(backend="watershed"))
    assert result.basic_stats["n_total"] == 0
    assert result.basic_stats["percentage"] is None
    assert np.isfinite(projections.dapi_mean).all()
    assert not result.images["ch2_thresh"].any()


def test_watershed_splits_touching_nuclei():
    image = np.zeros((150, 200), dtype=np.uint8)
    for center in [(75, 70), (75, 120)]:
        rr, cc = disk(center, 35, shape=image.shape)
        image[rr, cc] = 255
    config = AnalysisConfig(backend="watershed", min_nucleus_area=1000,
                            max_nucleus_area=5000, watershed_min_distance=30)
    assert len(Segmenter(config).generate(image)) == 2


def test_axis_order_and_explicit_time_position():
    array = np.zeros((2, 3, 4, 2, 15, 17), dtype=np.uint16)  # PTZCYX
    array[1, 2, :, 0] = np.arange(4)[:, None, None] * 100
    array[1, 2, :, 1] = np.arange(4)[:, None, None] * 50
    config = AnalysisConfig(time_index=2, position_index=1)
    p = project_array(array, "PTZCYX", config)
    np.testing.assert_array_equal(p.pnc_max, np.full((15, 17), 150))
    np.testing.assert_allclose(p.dapi_mean, 127.5)
    np.testing.assert_array_equal(p.dapi_max, np.zeros((15, 17)))
    p2 = project_array(np.transpose(array, (5, 1, 0, 3, 4, 2)), "XTPCYZ", config)
    np.testing.assert_array_equal(p.dapi_mean, p2.dapi_mean)
    with pytest.raises(ValueError, match="out of range"):
        project_array(array, "PTZCYX", replace(config, time_index=3))


@pytest.mark.parametrize("axes,shape", [("YXS", (5, 6, 3)), ("QCYX", (2, 2, 5, 6)),
                                       ("YYX", (2, 5, 6)), ("YX", (5, 6))])
def test_ambiguous_axes_rejected(axes, shape):
    with pytest.raises(ValueError):
        project_array(np.zeros(shape, dtype=np.uint16), axes)


def test_rounding_matches_matlab_uint8():
    np.testing.assert_array_equal(scale_uint8([0, 1, 2]), [0, 128, 255])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 1j])
def test_invalid_pixel_values_rejected(bad):
    array = np.full((2, 10, 12), bad)
    with pytest.raises(ValueError):
        project_array(array, "CYX")


@pytest.mark.parametrize("changes", [{"min_nucleus_area": 0}, {"max_nucleus_area": 2},
                                    {"neighborhood_size": 20}, {"positive_threshold": -1},
                                    {"positive_threshold": 1.1}, {"image_threshold": float("nan")},
                                    {"dapi_channel": 1}, {"points_per_batch": 0},
                                    {"score_threshold": 1.1}])
def test_invalid_settings_rejected(changes):
    with pytest.raises(ValueError):
        AnalysisConfig(**changes)


def test_settings_round_trip(tmp_path):
    config = AnalysisConfig(backend="watershed", time_index=2)
    path = tmp_path / "settings.json"
    config.save(path)
    assert AnalysisConfig.load(path) == config


def test_matlab_linear_svm_reference():
    fixture = json.loads((Path(__file__).parent / "fixtures/legacy_svm_vectors.json").read_text())
    scores = svm_decision(fixture["validation_x"])
    np.testing.assert_allclose(scores, np.array(fixture["validation_scores"])[:, 1], atol=1e-12)
    labels = np.array(load_legacy_svm()["classes"])[(scores >= 0).astype(int)]
    np.testing.assert_array_equal(labels, fixture["validation_predictions"])


def test_local_threshold_matlab_formula_and_bit_depth():
    rng = np.random.default_rng(4)
    image = rng.integers(100, 5000, (80, 90), dtype=np.uint16)
    config = AnalysisConfig()
    expected = image / 65535 > 1.59 * ndi.gaussian_filter(image / 65535, 21, mode="nearest", truncate=2)
    np.testing.assert_array_equal(threshold_pnc(image, config), expected)
    np.testing.assert_array_equal(threshold_pnc(image / 65535, config), expected)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        threshold_pnc(image.astype(float), config)


def test_mask_storage_and_matlab_index_conversion(tmp_path):
    projections, masks, _ = synthetic_image()
    path = tmp_path / "masks.npz"
    save_masks(path, masks, projections.dapi_max.shape)
    for a, b in zip(masks, load_masks(path, projections.dapi_max.shape)):
        np.testing.assert_array_equal(np.sort(a), b)
    with pytest.raises(ValueError, match="shape"):
        load_masks(path, (20, 30))
    h, w = projections.dapi_max.shape
    cells = np.empty((1, 2), dtype=object)
    for i, idx in enumerate(masks):
        yy, xx = np.unravel_index(idx, (h, w))
        cells[0, i] = yy + xx * h + 1
    mat_path = tmp_path / "masks.mat"
    savemat(mat_path, {"masks": {"ImageSize": [h, w], "NumObjects": 2, "PixelIdxList": cells}})
    for a, b in zip(masks, load_masks(mat_path, (h, w))):
        np.testing.assert_array_equal(np.sort(a), b)


def test_empty_mask_storage(tmp_path):
    path = tmp_path / "empty.npz"
    save_masks(path, [], (20, 30))
    assert load_masks(path, (20, 30)) == []


def test_rle_column_major_conversion():
    # Fortran order pixels 1,2,5 in a 3x2 image -> C order pixels 2,4,5.
    np.testing.assert_array_equal(_rle_indices({"size": [3, 2], "counts": [1, 2, 2, 1]}), [2, 4, 5])


def test_cache_invalidates_model_settings_but_not_pnc_threshold():
    image = np.zeros((30, 40), dtype=np.uint8)
    config = AnalysisConfig(backend="watershed")
    key = cache_fingerprint(image, config)
    assert key == cache_fingerprint(image, replace(config, positive_threshold=20))
    assert key != cache_fingerprint(image, replace(config, min_nucleus_area=4000))
    assert key != cache_fingerprint(image + 1, config)
    assert key == cache_fingerprint(image, replace(config, checkpoint="nonexistent-unused.pt"))


def test_export_empty_result(tmp_path):
    projections, _, config = synthetic_image()
    result = analyze(projections, config, masks=[])
    export_result(result, tmp_path)
    assert json.loads((tmp_path / "analysis.json").read_text())["summary"]["percentage"] is None
    assert (tmp_path / "visualization.png").is_file()
    assert (tmp_path / "nuclei.csv").read_text().count("\n") == 1
    with np.load(tmp_path / "images.npz", allow_pickle=False) as data:
        assert data["mask_overall"].dtype == np.uint32


def test_tiff_cli_and_failed_file_reporting(tmp_path):
    import tifffile

    projections, _, config = synthetic_image()
    image = tmp_path / "synthetic.ome.tif"
    tifffile.imwrite(image, np.stack([projections.dapi_max.astype(np.uint16), projections.pnc_max]),
                     metadata={"axes": "CYX"})
    settings = tmp_path / "settings.json"
    config.save(settings)
    output = tmp_path / "output"
    assert main([str(image), "--config", str(settings), "--output", str(output)]) == 0
    summary = (output / "summary.csv").read_text()
    assert "50.0" in summary
    rows, errors = run_batch([tmp_path / "missing.nd2"], config, tmp_path / "failed")
    assert not rows and len(errors) == 1
    assert json.loads((tmp_path / "failed/errors.json").read_text())


def test_no_silent_fallback_if_sam_checkpoint_missing():
    with pytest.raises((ValueError, RuntimeError), match="checkpoint|installed"):
        Segmenter(AnalysisConfig()).generate(np.zeros((20, 20), dtype=np.uint8))


def test_small_shape_perimeter():
    assert corrected_perimeter(np.ones((3, 3), dtype=bool)) == pytest.approx(7.476)
    assert corrected_perimeter(np.ones((1, 1), dtype=bool)) == 0


def test_instance_agreement_penalizes_missing_and_duplicate_instances():
    reference = np.zeros((10, 15), dtype=np.uint16)
    reference[1:4, 1:4] = 1
    reference[5:9, 6:10] = 2
    predicted = reference.copy()
    predicted[predicted == 2] = 0
    predicted[1:4, 11:14] = 5
    scores = compare_labels(reference, predicted)
    assert scores["matched"] == 1
    assert scores["precision"] == scores["recall"] == scores["f1"] == 0.5
    assert scores["mean_matched_iou"] == 1
    assert compare_labels(reference * 0, reference * 0)["f1"] is None


@pytest.mark.parametrize("number,positive,total", [(1, 67, 76), (2, 42, 45)])
def test_local_matlab_regression(number, positive, total):
    folder = Path(__file__).resolve().parents[1] / "pnc_counting/testfiles/testfiles"
    image = folder / f"IMG{number}.nd2"
    masks = folder / f"IMG{number}_segmentation.mat"
    if not image.is_file() or not masks.is_file():
        pytest.skip("Local ND2 reference data are not distributed")
    result = count_pnc(image, config=AnalysisConfig(backend="watershed", pnc_mode="pixels"), masks=masks)
    assert result.basic_stats["n_positive"] == positive
    assert result.basic_stats["n_total"] == total
