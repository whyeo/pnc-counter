"""Exploratory whole-field comparison, using the owner's existing frozen 30/70 split.

Run plan, tune, then validate. No validation field is measured during selection.
Private inputs and generated outputs belong under ignored validation/local/.
"""

import argparse
import hashlib
import json
import platform
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from skimage.segmentation import find_boundaries

from nucleus_analysis.adaptive_pnc import prepare_adaptive, select_adaptive
from nucleus_analysis.imaging import display_uint8
from nucleus_analysis.phenotype import assign_spots, pixel_size
from nucleus_analysis.projection_cache import read_cached
from nucleus_analysis.prominence_pnc import (
    ALGORITHM,
    MAPPING,
    prepare_prominence,
    select_prominence,
)
from nucleus_analysis.review import ReviewSession

GROUPS = ("PNC negative", "PNC positive", "PNC small")
METHODS = ("adaptive-v1", "dog-2d", "tophat-2d", "dog-z")
SENSITIVITIES = (25., 50., 75., 100.)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, document):
    Path(path).write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def source_identity():
    root = Path(__file__).resolve().parents[1]
    return {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "code_sha256": {str(p.relative_to(root)): digest(p) for p in
                            sorted((root / "src/nucleus_analysis").glob("*.py"))},
            "experiment_sha256": digest(__file__)}


def plan(split_path, output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "plan.json").exists():
        raise ValueError("Plan already exists; reuse it without changing the search")
    split = json.loads(split_path.read_text(encoding="utf-8"))
    write(output / "plan.json", {
        "schema": 1, "split_path": str(split_path.resolve()), "split_sha256": digest(split_path),
        "algorithm": ALGORITHM, "mapping": MAPPING, "source": source_identity(),
        "methods": METHODS, "sensitivities": SENSITIVITIES,
        "limits": {"spot_min_area": 3, "spot_max_area": 500, "spot_min_distance": 3, "min_spot_count": 1},
        "selection": "Maximize min(positive mean - negative mean, small mean - negative mean), then minimize negative mean. "
                     "Only dog-2d, tophat-2d, dog-z are eligible; adaptive-v1 is a comparator.",
        "proxy_screen": "Negative mean <= 70% of legacy, positive mean >= 85% of legacy, small mean >= legacy. "
                        "Passing this proxy does not establish visual preservation or accuracy.",
        "limitations": ["Exploratory: these validation fields have been examined previously.",
                        "Folder labels are sample groups, not punctum/nucleus truth.",
                        "No specimen independence or acquisition equivalence is assumed.",
                        "All original retained masks and exclusions are reported. Manual overrides are reported separately."],
        "split_counts": {g: {s: sum(c["group"] == g and c["split"] == s for c in split["cases"])
                             for s in ("tuning", "validation")} for g in GROUPS}})


def aggregate(rows):
    result = {}
    for group in GROUPS:
        selected = [r for r in rows if r["group"] == group]
        values = [100 * r["positive"] / r["total"] for r in selected if r["total"]]
        total = sum(r["total"] for r in selected)
        positive = sum(r["positive"] for r in selected)
        result[group] = {"fields": len(selected), "empty_fields": sum(r["total"] == 0 for r in selected),
                         "positive": positive, "total": total,
                         "mean_field_percent": float(np.mean(values)) if values else None,
                         "pooled_percent": 100 * positive / total if total else None,
                         "field_percent_min_q25_median_q75_max": list(map(float, np.percentile(values, [0, 25, 50, 75, 100]))) if values else []}
    return result


def measure(case, output, methods, sensitivities, visual=False):
    directory = Path(case["directory"])
    for name, expected in case["files"].items():
        if digest(directory / name) != expected:
            raise ValueError(f"Frozen export changed: {directory / name}")
    session = ReviewSession.open(directory)
    _, details = session.counts()
    ids = sorted(session.masks)
    accepted = [i for i in ids if not details[i]["rejected"]]
    masks = [session.masks[i].pixels for i in accepted]
    rows = [{"MaskID": i, "Area": len(session.masks[i].pixels), "BadMask": 0} for i in accepted]
    common = {"id": case["id"], "source": case["source"], "group": case["group"], "split": case["split"],
              "total": len(accepted), "rejected": len(ids)-len(accepted), "retained": len(ids),
              "manual_overrides": {str(i): session.masks[i].pnc_override for i in ids if session.masks[i].pnc_override is not None}}
    result = [{**common, "method": "legacy", "sensitivity": None,
               "positive": sum(details[i]["positive_pixels"] >= session.config.positive_threshold for i in accepted),
               "seconds": 0.}]
    measurements = []
    projection = session.projections
    for method in methods:
        started = time.perf_counter()
        if method == "dog-z":
            config = replace(session.config, pnc_mode="prominence", pnc_z_policy="auto")
            projection = read_cached(case["source"], config, cache=output / "cache")
            if not np.array_equal(projection.pnc_max, session.projections.pnc_max):
                raise ValueError("Raw maximum differs from the frozen export")
        p = projection if method == "dog-z" else session.projections
        calibration = pixel_size(session.config, p.metadata)
        if method == "adaptive-v1":
            features = prepare_adaptive(p.pnc_max, masks, accepted, calibration, 3)
            select = select_adaptive
        else:
            features = prepare_prominence(p.pnc_max, masks, accepted, calibration, 3,
                                           evidence=p.pnc_evidence if method == "dog-z" else {},
                                           z_policy="auto" if method == "dog-z" else "projection",
                                           variant="tophat" if method == "tophat-2d" else "dog")
            select = select_prominence
        elapsed = time.perf_counter() - started
        measurements.append({"method": method, "candidates": features.candidates,
                             "evidence": p.metadata.get("pnc_evidence"), "pixel_size_um": calibration})
        for sensitivity in sensitivities:
            _, labels, spots = select(features, sensitivity)
            counts = assign_spots(rows, masks, spots)
            result.append({**common, "method": method, "sensitivity": sensitivity,
                           "positive": sum(counts[i] >= 1 for i in accepted), "seconds": elapsed})
            if visual:
                render_case(output, case, p, session, labels, features, method, sensitivity)
        print(f"{case['split']} {case['group']} {Path(case['source']).name} {method}: {elapsed:.2f}s", flush=True)
    write(output / (case["id"] + "-" + case["split"] + "-measurements.json"), measurements)
    return result


def render_case(output, case, projection, session, labels, features, method, sensitivity):
    # Include strongest and weakest extracted candidates, plus a negative-call
    # example with the most legacy-positive pixels. Selection is stated here.
    chosen = sorted(features.candidates, key=lambda c: c["SignalScore"], reverse=True)
    centers = [(c["CentroidY"]-1, c["CentroidX"]-1, f"score {c['SignalScore']:.2f}; {c.get('ReviewFlags', '')}")
               for c in ([chosen[0], chosen[-1]] if chosen else [])]
    _, details = session.counts()
    if session.masks:
        identifier = max(session.masks, key=lambda i: details[i]["positive_pixels"])
        yy, xx = np.unravel_index(session.masks[identifier].pixels, session.shape)
        centers.append((yy.mean(), xx.mean(), f"nucleus {identifier}; legacy pixels {details[identifier]['positive_pixels']}"))
    limits = tuple(np.percentile(projection.pnc_max, (1, 99.7)))
    gray = display_uint8(projection.pnc_max, limits)
    raw = np.repeat(gray[..., None], 3, axis=-1)
    overlay = raw.copy()
    overlay[find_boundaries(labels, mode="inner")] = (40, 255, 100)
    overlay[find_boundaries(session._adaptive_features.labels if session._adaptive_features is not None else np.zeros(gray.shape), mode="inner")] = (255, 200, 20)
    evidence = np.repeat(display_uint8(projection.pnc_evidence["score"], (0, 20))[..., None], 3, axis=-1) if projection.pnc_evidence else raw
    panel = Image.new("RGB", (600, max(1, len(centers))*235), "#202020")
    draw = ImageDraw.Draw(panel)
    for i, (y, x, title) in enumerate(centers):
        cy, cx = int(y), int(x)
        draw.text((5, i*235+2), title[:95], fill="white")
        evidence_title = "Per-plane score (0..20)" if projection.pnc_evidence else "Projection; no Z evidence"
        for j, (array, name) in enumerate(((raw, "Raw: same display range"), (overlay, "Accepted boundaries"), (evidence, evidence_title))):
            crop = array[max(0, cy-45):cy+46, max(0, cx-45):cx+46]
            tile = Image.fromarray(crop).resize((196, 196))
            panel.paste(tile, (j*200, i*235+35))
            draw.text((j*200+2, i*235+18), name, fill="white")
    folder = output / "visuals"
    folder.mkdir(exist_ok=True)
    panel.save(folder / f"{case['group']}-{Path(case['source']).stem}-{method}-{sensitivity:g}.png")


def run(stage, output):
    spec = json.loads((output / "plan.json").read_text(encoding="utf-8"))
    if source_identity()["code_sha256"] != spec["source"]["code_sha256"] or digest(__file__) != spec["source"]["experiment_sha256"]:
        raise ValueError("Implementation changed after the plan; create a new versioned experiment directory")
    split_path = Path(spec["split_path"])
    if digest(split_path) != spec["split_sha256"]:
        raise ValueError("Split changed")
    cases = json.loads(split_path.read_text(encoding="utf-8"))["cases"]
    subset = "tuning" if stage == "tune" else "validation"
    if (output / f"{subset}.json").exists():
        raise ValueError("Completed comparison is immutable; choose a new output directory")
    frozen = None if stage == "tune" else json.loads((output / "frozen.json").read_text())
    methods = spec["methods"] if frozen is None else ("adaptive-v1", frozen["method"])
    levels = spec["sensitivities"] if frozen is None else sorted({50., frozen["sensitivity"]})
    results = []
    for case in cases:
        if case["split"] == subset:
            results.extend(measure(case, output, methods, levels, visual=frozen is not None))
    summary = {"legacy": aggregate([r for r in results if r["method"] == "legacy"])}
    scores = []
    for method in methods:
        for level in levels:
            value = aggregate([r for r in results if r["method"] == method and r["sensitivity"] == level])
            summary[f"{method}@{level:g}"] = value
            neg, pos, small = [value[g]["mean_field_percent"] for g in GROUPS]
            if method != "adaptive-v1":
                scores.append((min(pos-neg, small-neg), -neg, method, level, value))
    write(output / f"{subset}.json", {"source": spec["source"], "results": results, "summary": summary,
          "hardware": {"platform": platform.platform(), "processor": platform.processor(),
                       "numpy": np.__version__, "cache": "read-through cache; cold unless stated in log"}})
    if stage == "tune":
        _, _, method, level, value = max(scores, key=lambda row: (row[0], row[1]))
        baseline = summary["legacy"]
        n, p, s = [value[g]["mean_field_percent"] for g in GROUPS]
        bn, bp, bs = [baseline[g]["mean_field_percent"] for g in GROUPS]
        write(output / "frozen.json", {"method": method, "sensitivity": level, "algorithm": ALGORITHM,
              "mapping": MAPPING, "tuning_proxy_passed": n <= .7*bn and p >= .85*bp and s >= bs,
              "adopted_as_default": False, "reason": "Visual preservation and owner approval remain required.",
              "source": spec["source"], "tuning_sha256": digest(output / "tuning.json")})
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "tune", "validate"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--split", type=Path)
    args = parser.parse_args()
    if args.stage == "plan":
        if args.split is None:
            parser.error("plan requires --split")
        plan(args.split, args.output)
    else:
        run(args.stage, args.output)


if __name__ == "__main__":
    main()
