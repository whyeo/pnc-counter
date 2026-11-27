import json

import numpy as np
import pytest
import tifffile

from nucleus_analysis import AnalysisConfig, analyze
from nucleus_analysis.editor import render_review
from nucleus_analysis.imaging import project_array
from nucleus_analysis.output import export_result, overlay
from nucleus_analysis.review import ReviewSession


@pytest.fixture
def review_data():
    dapi = np.arange(120 * 180, dtype=np.uint16).reshape(120, 180)
    pnc = np.zeros_like(dapi)
    pnc[10, 10:22] = 5000
    pnc[85, 120:132] = 5000
    masks = []
    for y, x in [(10, 10), (50, 70)]:
        yy, xx = np.mgrid[y:y + 21, x:x + 21]
        masks.append(np.ravel_multi_index((yy.ravel(), xx.ravel()), dapi.shape))
    projections = project_array(np.stack([dapi, pnc]), "CYX")
    config = AnalysisConfig(backend="watershed", min_nucleus_area=100,
                            max_nucleus_area=2000, threshold_mode="global")
    result = analyze(projections, config, masks)
    return projections, config, result


def session_from(data):
    projections, config, result = data
    return ReviewSession(projections, config, result.masks, result.full_stats)


def test_add_redraw_and_immediate_recount(review_data):
    session = session_from(review_data)
    assert session.counts()[0]["n_positive"] == 1
    session.redraw(1, [(10, 11), (30, 11), (30, 30), (10, 30)])
    assert session.counts()[0]["n_positive"] == 0
    assert session.masks[1].edited
    identifier = session.add([(120, 80), (135, 80), (135, 95), (120, 95)])
    assert identifier == 3
    counts, _ = session.counts()
    assert counts["n_positive"] == 1 and counts["n_total"] == 3
    assert session.result().basic_stats == counts
    assert [r["MaskID"] for r in session.result().full_stats] == [1, 2, 3]


def test_flagging_does_not_exclude_and_rejection_does(review_data):
    session = session_from(review_data)
    session.mark([1], flagged=True)
    assert session.counts()[0]["n_flagged"] == 1
    assert session.counts()[0]["n_positive"] == 1
    session.mark([1], rejected=True)
    assert session.counts()[0]["n_total"] == 1
    assert session.result().basic_stats["n_positive"] == 0
    assert session.result().full_stats[0]["BadMask"] == 1
    assert session.undo()
    assert session.counts()[0]["n_positive"] == 1
    assert session.redo()
    assert session.counts()[0]["n_positive"] == 0
    session.mark([1], rejected=False)
    assert session.counts()[0]["n_total"] == 2


def test_delete_undo_redo_reset_and_id_preservation(review_data):
    session = session_from(review_data)
    assert not session.dirty
    session.delete([1])
    assert set(session.masks) == {2}
    assert session.dirty
    session.undo()
    assert set(session.masks) == {1, 2}
    assert not session.dirty
    session.redo()
    assert set(session.masks) == {2}
    session.reset()
    assert set(session.masks) == {1, 2}
    assert not session.dirty
    session.undo()
    assert set(session.masks) == {2}


def test_split_conserves_pixels_and_merge_restores_geometry(review_data):
    session = session_from(review_data)
    original = session.masks[1].pixels.copy()
    ids = session.split(1, [(10, 10), (20, 10), (20, 30), (10, 30)])
    assert ids == (1, 3)
    assert not np.intersect1d(session.masks[1].pixels, session.masks[3].pixels).size
    np.testing.assert_array_equal(np.union1d(session.masks[1].pixels, session.masks[3].pixels), original)
    assert session.counts()[0]["n_total"] == 3
    assert session.counts()[0]["n_positive"] == 1
    assert session.merge(ids) == 1
    assert session.counts()[0]["n_total"] == 2
    np.testing.assert_array_equal(session.masks[1].pixels, original)
    assert session.masks[1].sources == (1,)
    session.undo()
    assert set(session.masks) == {1, 2, 3}


@pytest.mark.parametrize("points", [[], [(1, 1), (2, 2)], [(1, 1), (2, 2), (3, 3)],
                                    [(-1, 1), (10, 1), (10, 10)],
                                    [(1, 1), (float("nan"), 2), (5, 7)]])
def test_invalid_outlines_leave_review_unchanged(review_data, points):
    session = session_from(review_data)
    with pytest.raises(ValueError):
        session.add(points)
    assert not session.dirty and not session.history


def test_overlapping_outline_is_rejected_without_stealing_pixels(review_data):
    session = session_from(review_data)
    original = session.masks[1].pixels.copy()
    with pytest.raises(ValueError, match="overlaps nucleus 1"):
        session.add([(15, 15), (40, 15), (40, 40), (15, 40)])
    with pytest.raises(ValueError, match="overlaps nucleus 2"):
        session.redraw(1, [(70, 50), (90, 50), (90, 70), (70, 70)])
    np.testing.assert_array_equal(session.masks[1].pixels, original)
    assert not session.dirty


def test_invalid_split_and_merge_are_atomic(review_data):
    session = session_from(review_data)
    with pytest.raises(ValueError, match="two connected parts"):
        session.split(1, [(1, 1), (40, 1), (40, 40), (1, 40)])
    with pytest.raises(ValueError, match="at least two"):
        session.merge([1])
    assert not session.dirty


def test_review_round_trip_is_self_contained_and_original_is_untouched(review_data, tmp_path):
    _, _, result = review_data
    original = tmp_path / "original"
    export_result(result, original)
    hashes = {path.name: path.read_bytes() for path in original.iterdir()}
    session = ReviewSession.open(original)
    session.mark([1], rejected=True, flagged=True)
    session.redraw(2, [(70, 51), (90, 51), (90, 70), (70, 70)])
    first, counts = session.save(tmp_path / "reviews")
    assert counts["n_total"] == 1 and counts["n_flagged"] == 1
    assert not session.dirty
    assert all((original / name).read_bytes() == value for name, value in hashes.items())
    reopened = ReviewSession.open(first)
    assert not reopened.dirty
    assert reopened.counts()[0] == counts
    assert reopened.history == session.history
    assert reopened.masks[1].rejected and reopened.masks[1].flagged
    assert reopened.masks[2].edited
    assert reopened.result().basic_stats == counts
    labels = tifffile.imread(first / "reviewed_labels.tif")
    assert labels.dtype == np.uint32 and set(np.unique(labels)) == {0, 2}
    assert "ReviewFlag" in (first / "nuclei.csv").read_text()
    assert json.loads((first / "review.json").read_text())["schema_version"] == 2
    # Original raw image files and the old output directory are not needed.
    reopened.original_directory = tmp_path / "no-longer-present"
    reopened.reset()
    assert reopened.counts()[0]["n_total"] == 2
    assert reopened.counts()[0]["n_positive"] == 1
    second, _ = reopened.save(tmp_path / "reviews")
    assert first != second and first.is_dir() and second.is_dir()


def test_fully_deleted_review_saves_and_reopens(review_data, tmp_path):
    session = session_from(review_data)
    session.delete([1, 2])
    path, stats = session.save(tmp_path)
    assert stats["percentage"] is None and stats["n_total"] == 0
    reopened = ReviewSession.open(path)
    assert reopened.counts()[0] == stats
    reopened.reset()
    assert reopened.counts()[0]["n_total"] == 2


def test_review_checksum_detects_modified_masks(review_data, tmp_path):
    session = session_from(review_data)
    path, _ = session.save(tmp_path)
    with (path / "nuclei_masks.npz").open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        ReviewSession.open(path)


def test_legacy_export_without_candidates_warns_and_reopens(review_data, tmp_path):
    _, _, result = review_data
    result.masks = None
    export_result(result, tmp_path)
    session = ReviewSession.open(tmp_path)
    assert session.warning
    assert session.counts()[0]["n_total"] == 2


def test_manual_acceptance_overrides_automatic_quality_filter(review_data, monkeypatch):
    session = session_from(review_data)
    monkeypatch.setattr("nucleus_analysis.pipeline.is_bad_mask", lambda _row: True)
    # Reviewer state, rather than a fresh automatic rejection, is authoritative.
    assert session.result().basic_stats["n_total"] == 2
    session.mark([1], rejected=True)
    assert session.result().basic_stats["n_total"] == 1


def test_render_layers_include_selected_and_flagged_boundaries(review_data):
    session = session_from(review_data)
    session.mark([1], flagged=True)
    image = np.asarray(render_review(session))
    assert np.any(np.all(image == (255, 220, 20), axis=-1))
    selected = np.asarray(render_review(session, selected=[1]))
    assert np.any(np.all(selected == (110, 255, 110), axis=-1))
    assert render_review(session, channel="PNC", show_masks=False).size == (180, 120)
    exported = np.asarray(overlay(session.result()))
    assert np.any(np.all(exported == (255, 220, 20), axis=-1))


def test_failed_save_keeps_edits_and_does_not_publish_a_partial_revision(review_data, tmp_path, monkeypatch):
    session = session_from(review_data)
    session.delete([1])

    def fail_export(*_args, **_kwargs):
        raise OSError("Disk unavailable")

    monkeypatch.setattr("nucleus_analysis.review.export_result", fail_export)
    with pytest.raises(OSError, match="Disk unavailable"):
        session.save(tmp_path)
    assert session.dirty
    assert not list(tmp_path.glob("review-*"))


def test_accepting_an_overlapping_rejected_detection_requires_correction(review_data):
    projections, config, result = review_data
    rows = [*result.full_stats, {**result.full_stats[0], "MaskID": 3, "BadMask": 1}]
    session = ReviewSession(projections, config, [*result.masks, result.masks[0]], rows)
    with pytest.raises(ValueError, match="overlaps accepted nucleus"):
        session.mark([3], rejected=False)
    assert session.masks[3].rejected
    assert session.counts()[0]["n_total"] == 2
