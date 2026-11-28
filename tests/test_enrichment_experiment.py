"""Before/after denominators, manual-call separation and no held-out tuning."""

from types import SimpleNamespace

import numpy as np
import pytest

from nucleus_analysis import AnalysisConfig
from nucleus_analysis.pipeline import threshold_pnc
from tools.enrichment_experiment import (
    AFTER,
    GROUPS,
    LEVELS,
    aggregate,
    evaluate,
    select_operating_points,
    stable_threshold,
)


def test_stable_threshold_is_replayed_exactly_on_fixed_raw_pixels():
    image = np.random.default_rng(9).integers(0, 1500, (80, 90), dtype=np.uint16)
    config = AnalysisConfig()
    np.testing.assert_array_equal(stable_threshold()(image, config), threshold_pnc(image, config))


def test_selection_is_development_only_and_freezes_preservation_before_negative_reduction():
    rows = []
    for group, count in zip(GROUPS, (2, 8, 2)):
        rows.append({"method": "stable-legacy", "group": group, "split": "development",
                     "automatic_positive": count, "total": 10, "excluded": 0, "manual_overrides": 0})
    for method in AFTER:
        for level, counts in zip(LEVELS, ((0, 1, 0), (0, 3, 0), (1, 7, 2), (5, 8, 5), (9, 10, 9))):
            for group, count in zip(GROUPS, counts):
                rows.append({"method": method, "sensitivity": level, "group": group, "split": "development",
                             "automatic_positive": count, "total": 10, "excluded": 0, "manual_overrides": 0})
    frozen = select_operating_points(rows)
    assert all(v["sensitivity"] == 50 and v["proxy_screen_passed"] for v in frozen.values())
    with pytest.raises(ValueError, match="validation"):
        select_operating_points(rows + [{"split": "validation"}])


def test_field_means_pooled_denominators_and_overrides_are_distinct():
    rows = [{"group": GROUPS[0], "automatic_positive": 1, "total": 1, "excluded": 0, "manual_overrides": 0},
            {"group": GROUPS[0], "automatic_positive": 0, "total": 9, "excluded": 1, "manual_overrides": 0}]
    result = aggregate(rows)[GROUPS[0]]
    assert result["field_mean"] == 50 and result["pooled_percent"] == 10
    masks = {1: SimpleNamespace(pnc_override=False), 2: SimpleNamespace(pnc_override=True),
             3: SimpleNamespace(pnc_override=None)}
    case = {"id": "test", "group": GROUPS[0], "split": "development", "source": "unused"}
    field, nuclei = evaluate(None, case, SimpleNamespace(masks=masks), [1, 2], [np.array([1]), np.array([2])],
                             "stable-legacy", None, {1: True, 2: False}, seconds=0)
    assert field["automatic_positive"] == 1 and field["effective_positive"] == 1
    assert [r["automatic_positive"] for r in nuclei] == [1, 0]
    assert [r["effective_positive"] for r in nuclei] == [0, 1]
    assert field["total"] == 2 and field["excluded"] == 1
