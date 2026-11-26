"""Replay local MATLAB masks, compare independent projections/features, save evidence."""

import argparse
import csv
import json
import platform
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from nucleus_analysis import AnalysisConfig, analyze
from nucleus_analysis.imaging import read_image
from nucleus_analysis.output import export_result
from nucleus_analysis.quality import load_legacy_svm, svm_decision
from nucleus_analysis.segmentation import load_masks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("pnc_counting/testfiles/testfiles"))
    parser.add_argument("--reference", type=Path, default=Path("validation/local"))
    parser.add_argument("--output", type=Path, default=Path("validation/local/baseline"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {"python": platform.python_version(), "reference_kind": "MATLAB cached SAM masks and recorded counts",
                "quality_filter": "none (matches the legacy GUI, which never called loadSVMModel)",
                "images": []}
    all_passed = True
    for number, expected_positive, expected_total in [(1, 67, 76), (2, 42, 45)]:
        name = f"IMG{number}"
        image = args.data / f"{name}.nd2"
        mask_path = args.data / f"{name}_segmentation.mat"
        config = AnalysisConfig()
        projections = read_image(image, config)
        result = analyze(projections, config, masks=load_masks(mask_path, projections.dapi_max.shape))
        record = {"image": image.name, "counts": result.basic_stats,
                  "expected_positive": expected_positive, "expected_total": expected_total,
                  "counts_match": result.basic_stats["n_positive"] == expected_positive
                                  and result.basic_stats["n_total"] == expected_total}
        export_result(result, args.output / name,
                      provenance={"kind": "imported", "path": str(mask_path.resolve())})
        ref_path = args.reference / f"{name}_matlab.mat"
        if ref_path.is_file():
            reference = loadmat(ref_path)
            record["projection_max_absolute_errors"] = {
                key: float(np.abs(values.astype(float) - reference[key].astype(float)).max())
                for key, values in [("dapi_max", projections.dapi_max),
                                    ("dapi_mean", projections.dapi_mean), ("ch2", projections.pnc_max)]}
            record["threshold_mismatched_pixels"] = int(np.count_nonzero(
                result.images["ch2_thresh"] != reference["local_mask"]))
            with (args.reference / f"{name}_matlab.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            if len(rows) != len(result.full_stats):
                raise ValueError(f"{name}: feature-row counts differ")
            record["feature_max_absolute_errors"] = {
                key: max(abs(float(a[key]) - float(b[key])) for a, b in zip(result.full_stats, rows))
                for key in rows[0]}
            features = load_legacy_svm()["features"]
            python_scores = svm_decision([[r[k] for k in features] for r in result.full_stats])
            matlab_scores = svm_decision([[float(r[k]) for k in features] for r in rows])
            record["svm_feature_prediction_disagreements"] = int(np.count_nonzero(
                (python_scores >= 0) != (matlab_scores >= 0)))
            record["reference_checks_passed"] = (
                all(error == 0 for error in record["projection_max_absolute_errors"].values())
                and record["threshold_mismatched_pixels"] == 0
                and all(error < (0.003 if key == "Solidity" else 1e-9)
                        for key, error in record["feature_max_absolute_errors"].items())
                and record["svm_feature_prediction_disagreements"] == 0)
            all_passed &= record["reference_checks_passed"]
        else:
            record["independent_matlab_reference"] = "unavailable; run tools/export_matlab_reference.m"
        all_passed &= record["counts_match"]
        evidence["images"].append(record)
        print(f"{name}: {result.basic_stats['n_positive']} / {result.basic_stats['n_total']}; "
              f"counts match: {record['counts_match']}", flush=True)
    (args.output / "baseline.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
