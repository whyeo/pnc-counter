"""Research protocol guards: no held-out tuning or assumed cell truth."""

import json

import numpy as np
import pytest

from tools.pnc_control_experiment import GROUPS, fit, prepare, spot_features


def test_local_spot_scores_ignore_constant_background_and_find_small_signal():
    y, x = np.mgrid[:81, :81]
    pixels = np.flatnonzero((y-40)**2 + (x-40)**2 < 35**2)
    assert not spot_features(np.full((81, 81), 100.0), pixels, .1)
    rng = np.random.default_rng(19)
    image = 100 + rng.normal(0, .5, (81, 81))
    image += 50 * np.exp(-((y-35)**2 + (x-45)**2) / 8)
    peaks = spot_features(image, pixels, .1)
    assert any(contrast > 1.1 and snr > 10 and abs(py-35) <= 2 and abs(px-45) <= 2
               for contrast, snr, _, _, py, px in peaks)


def test_split_is_30_70_by_field_and_rejects_duplicate_projections(tmp_path):
    root = tmp_path / "exports"
    index = 0
    for group, count in zip(GROUPS, (10, 17, 10)):
        for number in range(1, count+1):
            index += 1
            folder = root / str(index)
            folder.mkdir(parents=True)
            (folder / "analysis.json").write_text(json.dumps({"input": {
                "source": str(tmp_path / group / f"IMG{number}.nd2")}}))
            np.savez(folder / "images.npz", ch1_max=np.full((3, 3), index), ch2=np.full((3, 3), index))
            for name in ("nuclei.csv", "nuclei_masks.npz"):
                (folder / name).write_bytes(b"fixture")
    first = prepare([root], tmp_path / "first")
    second = prepare([root], tmp_path / "second")
    assert first == second
    tuning = [c for c in first["cases"] if c["split"] == "tuning"]
    assert len(tuning) == 11
    assert [sum(c["group"] == g for c in tuning) for g in GROUPS] == [3, 5, 3]
    assert sum(c["split"] == "validation" for c in first["cases"]) == 26
    with pytest.raises(ValueError, match="already exists"):
        prepare([root], tmp_path / "first")
    (root / "2/images.npz").write_bytes((root / "1/images.npz").read_bytes())
    with pytest.raises(ValueError, match="Duplicate"):
        prepare([root], tmp_path / "duplicate")


def test_parameter_selection_does_not_read_validation_cells(tmp_path):
    class HeldOut:
        def __iter__(self):
            pytest.fail("Validation cells leaked into tuning")

    (tmp_path / "split.json").write_text("frozen split")
    (tmp_path / "features.json").write_text("frozen features")
    cases = [{"id": str(i), "group": g, "source": f"{i}.nd2", "split": "tuning"}
             for i, g in enumerate(GROUPS)]
    cases.append({"id": "heldout", "group": GROUPS[0], "split": "validation"})
    features = {"cases": [
        {"id": "0", "cells": [{"baseline": 1, "pixels": 20, "peaks": []}]},
        {"id": "1", "cells": [{"baseline": 1, "pixels": 100, "peaks": [[2., 20., 10, .1, 5, 5]]}]},
        {"id": "2", "cells": [{"baseline": 0, "pixels": 2, "peaks": [[2., 20., 10, .1, 5, 5]]}]},
        {"id": "heldout", "cells": HeldOut()},
    ]}
    selected = fit({"cases": cases}, features, tmp_path)
    assert not selected["validation_used_for_selection"]
    assert selected["parameters"]["method"] == "local_spots"
    assert selected["objective_gap"] == 1
    with pytest.raises(ValueError, match="already frozen"):
        fit({"cases": cases}, features, tmp_path)
