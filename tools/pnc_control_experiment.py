"""Research-only, field-held-out comparison of PNC rules on exported controls.

Folder labels are weak image-level labels, never per-cell biological truth.
This tool never changes application preferences, images, or released defaults.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

GROUPS = ("PNC negative", "PNC positive", "PNC small")
SCALES_UM = (0.10, 0.20, 0.40)
CONTRASTS = (1.05, 1.10, 1.20, 1.35, 1.50)
SIGNALS = (3, 4, 5, 6, 8, 10, 12, 16)
MIN_AREAS = (1, 3, 5)


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def prepare(roots, output, seed=20261127):
    """Freeze whole fields before any candidate parameter search."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "split.json"
    if target.exists():
        raise ValueError("Split already exists; use it rather than redrawing the holdout")
    cases, seen = [], set()
    for root in roots:
        for path in sorted(Path(root).glob("*/analysis.json")):
            metadata = json.loads(path.read_text(encoding="utf-8"))
            source = Path(metadata["input"]["source"])
            if source.parent.name not in GROUPS:
                continue
            with np.load(path.parent / "images.npz", allow_pickle=False) as images:
                digest = hashlib.sha256()
                for key in ("ch1_max", "ch2"):
                    array = images[key]
                    digest.update(str((key, array.shape, array.dtype.str)).encode())
                    digest.update(array.tobytes())
            identity = digest.hexdigest()
            if identity in seen:
                raise ValueError(f"Duplicate projected field: {source}; group duplicates before splitting")
            seen.add(identity)
            cases.append({"id": identity, "group": source.parent.name, "source": str(source.resolve()),
                          "directory": str(path.parent.resolve()), "files": {
                              name: sha256(path.parent / name) for name in
                              ("analysis.json", "images.npz", "nuclei.csv", "nuclei_masks.npz")}})
    rng = np.random.default_rng(seed)
    # These fields were visually inspected during problem diagnosis. They must
    # stay in tuning, rather than being described as previously unseen holdout.
    inspected = {("PNC negative", "IMG2.nd2"), ("PNC small", "IMG1.nd2")}
    for group in GROUPS:
        selected = sorted((c for c in cases if c["group"] == group), key=lambda c: c["id"])
        if len(selected) < 3:
            raise ValueError(f"Need at least three fields in {group}")
        n_tune = max(1, int(np.floor(0.30 * len(selected) + 0.5)))
        forced = [c for c in selected if (group, Path(c["source"]).name) in inspected]
        remaining = [c for c in selected if c not in forced]
        order = rng.permutation(len(remaining))
        tune_ids = {c["id"] for c in forced}
        tune_ids.update(remaining[i]["id"] for i in order[:n_tune - len(forced)])
        for case in selected:
            case["split"] = "tuning" if case["id"] in tune_ids else "validation"
    protocol = {"schema": 1, "seed": seed, "tuning_fraction": 0.30,
                "unit": "whole image field", "cases": cases,
                "limitations": ["Folder labels are not per-nucleus reference calls.",
                    "Specimen/acquisition relationships are unknown; independence is unverified.",
                    "Baseline summaries were inspected before splitting; inspected images stay in tuning.",
                    "Small-PNC fields are treated as a positive-control challenge, not all-positive nuclei."],
                "search_space": {"scales_um": SCALES_UM, "contrast": CONTRASTS,
                                 "snr": SIGNALS, "min_area_pixels": MIN_AREAS},
                "selection": "Maximize the weaker positive/small group mean call-rate gap above negative; "
                             "field means weight groups equally; break ties by lower negative rate.",
                "baseline": "Frozen exported SAM geometry and original default PNC calls"}
    save(target, protocol)
    print(json.dumps({g: {s: sum(c["group"] == g and c["split"] == s for c in cases)
                         for s in ("tuning", "validation")} for g in GROUPS}), flush=True)
    return protocol


def spot_features(image, pixels, pixel_size_um):
    """Multiscale local peaks relative to intranuclear background and MAD noise.

    Mask-normalized Gaussian filtering prevents dark pixels outside a nucleus
    from manufacturing a bright boundary. Scores are research measurements,
    not calibrated probabilities or confirmation of perinucleolar location.
    """
    yy, xx = np.unravel_index(pixels, image.shape)
    y0, x0, y1, x1 = yy.min(), xx.min(), yy.max() + 1, xx.max() + 1
    mask = np.zeros((y1-y0, x1-x0), dtype=bool)
    mask[yy-y0, xx-x0] = True
    values = np.asarray(image[y0:y1, x0:x1], dtype=float)
    interior = ndi.binary_erosion(mask, iterations=max(1, round(0.2 / pixel_size_um)), border_value=0)
    if not interior.any():
        return []

    def smooth(sigma):
        weight = ndi.gaussian_filter(mask.astype(float), sigma, mode="constant")
        numerator = ndi.gaussian_filter(values * mask, sigma, mode="constant")
        return np.divide(numerator, weight, out=np.zeros_like(values), where=weight > 1e-9)

    background = smooth(1.0 / pixel_size_um)
    peaks = []
    for scale in SCALES_UM:
        smoothed = smooth(max(0.5, scale / pixel_size_um))
        response = smoothed - background
        centered = response[interior] - np.median(response[interior])
        noise = max(1.4826 * float(np.median(np.abs(centered))), 1e-6)
        maxima = (response == ndi.maximum_filter(response, size=5)) & interior & (response > 0)
        # A permissive, fixed extraction floor allows later thresholds to be
        # chosen using tuning fields only, without rerunning feature extraction.
        for y, x in np.argwhere(maxima & (response / noise >= min(SIGNALS))):
            radius = max(1, round(2 * scale / pixel_size_um))
            patch = response[max(0, y-radius):y+radius+1, max(0, x-radius):x+radius+1]
            area = int(np.count_nonzero(patch >= response[y, x] / 2))
            peaks.append([float(smoothed[y, x] / max(background[y, x], 1e-6)),
                          float(response[y, x] / noise), area, scale, int(y+y0), int(x+x0)])
    return peaks


def extract(protocol, output):
    from nucleus_analysis.segmentation import load_masks

    output = Path(output)
    result = {"split_sha256": sha256(output / "split.json"), "cases": []}
    for case in protocol["cases"]:
        directory = Path(case["directory"])
        for name, expected in case["files"].items():
            if sha256(directory / name) != expected:
                raise ValueError(f"Export changed: {directory / name}")
        metadata = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
        sizes = metadata["input"].get("pixel_size_um", {})
        if not sizes.get("x") or not np.isclose(sizes["x"], sizes.get("y", 0)):
            raise ValueError("This research protocol requires calibrated isotropic pixels")
        with np.load(directory / "images.npz", allow_pickle=False) as data:
            marker = data["ch2"]
        masks = load_masks(directory / "nuclei_masks.npz", marker.shape)
        with (directory / "nuclei.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != len(masks):
            raise ValueError("Mask/measurement mismatch")
        cells = [{"id": int(row["MaskID"]), "baseline": int(row["Positive"]),
                  "pixels": int(row["NumberCh2PixelsPositive"]),
                  "peaks": spot_features(marker, pixels, sizes["x"])}
                 for row, pixels in zip(rows, masks) if not int(row["BadMask"])]
        result["cases"].append({"id": case["id"], "cells": cells})
        print(f"Extracted {case['group']} / {Path(case['source']).name}: {len(cells)} nuclei", flush=True)
    save(output / "features.json", result)
    return result


def call(cell, parameters):
    if parameters["method"] == "pixels":
        return cell["pixels"] >= parameters["cutoff"]
    return any(contrast >= parameters["contrast"] and snr >= parameters["snr"] and area >= parameters["min_area"]
               for contrast, snr, area, *_ in cell["peaks"])


def rates(cases, features, parameters):
    by_id = {c["id"]: c for c in features["cases"]}
    groups = {g: [] for g in GROUPS}
    fields = []
    for case in cases:
        cells = by_id[case["id"]]["cells"]
        if not cells:
            raise ValueError("Empty fields need an explicit review decision before this comparison")
        calls = sum(c["baseline"] if parameters is None else call(c, parameters) for c in cells)
        rate = calls / len(cells)
        groups[case["group"]].append(rate)
        fields.append({"id": case["id"], "group": case["group"], "source": case["source"],
                       "nuclei": len(cells), "positive": calls, "rate": rate})
    return {g: float(np.mean(values)) for g, values in groups.items()}, fields


def fit(protocol, features, output):
    output = Path(output)
    if (output / "selected.json").exists():
        raise ValueError("Parameters already frozen; do not tune again after inspecting validation")
    tuning = [c for c in protocol["cases"] if c["split"] == "tuning"]
    candidates = [{"method": "pixels", "cutoff": n} for n in (3, 5, 10, 20, 30, 50, 100)]
    candidates += [{"method": "local_spots", "contrast": c, "snr": s, "min_area": a}
                   for c in CONTRASTS for s in SIGNALS for a in MIN_AREAS]
    scored = []
    for parameters in candidates:
        means, _ = rates(tuning, features, parameters)
        gap = min(means["PNC positive"], means["PNC small"]) - means["PNC negative"]
        scored.append((gap, -means["PNC negative"], parameters, means))
    best = max(scored, key=lambda item: item[:2])
    selected = {"split_sha256": sha256(output / "split.json"),
                "features_sha256": sha256(output / "features.json"), "parameters": best[2],
                "tuning_group_mean_call_rates": best[3], "objective_gap": best[0],
                "candidate_count": len(candidates), "validation_used_for_selection": False}
    save(output / "selected.json", selected)
    print(json.dumps(selected, indent=2), flush=True)
    return selected


def validate(protocol, features, selected, output):
    output = Path(output)
    if sha256(output / "split.json") != selected["split_sha256"]:
        raise ValueError("Split changed after tuning")
    if sha256(output / "features.json") != selected["features_sha256"]:
        raise ValueError("Features changed after tuning")
    cases = [c for c in protocol["cases"] if c["split"] == "validation"]
    baseline, baseline_fields = rates(cases, features, None)
    candidate, candidate_fields = rates(cases, features, selected["parameters"])
    report = {"parameters": selected["parameters"], "split_sha256": selected["split_sha256"],
              "selected_sha256": sha256(output / "selected.json"), "validation_fields": len(cases),
              "limitations": protocol["limitations"], "baseline_group_mean_call_rates": baseline,
              "candidate_group_mean_call_rates": candidate,
              "baseline_fields": baseline_fields, "candidate_fields": candidate_fields}
    save(output / "validation.json", report)
    print(json.dumps({k: v for k, v in report.items() if not k.endswith("_fields")}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "extract", "fit", "validate"))
    parser.add_argument("--results", nargs="*", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.results or [], args.output)
        return
    protocol = json.loads((args.output / "split.json").read_text(encoding="utf-8"))
    if args.stage == "extract":
        extract(protocol, args.output)
        return
    features = json.loads((args.output / "features.json").read_text(encoding="utf-8"))
    if features["split_sha256"] != sha256(args.output / "split.json"):
        raise ValueError("Split changed after feature extraction")
    if args.stage == "fit":
        fit(protocol, features, args.output)
    else:
        selected = json.loads((args.output / "selected.json").read_text(encoding="utf-8"))
        validate(protocol, features, selected, args.output)


if __name__ == "__main__":
    main()
