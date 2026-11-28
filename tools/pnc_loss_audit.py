"""Versioned dev2 loss audit and immutable exploratory 60/40 field manifest.

The audited detector is extracted from the exact baseline Git object. Named,
one-at-a-time edits instrument it without changing the production dev2 protocol.
No audit category is a biological label.
"""

import argparse
import csv
import dataclasses
import hashlib
import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np

from nucleus_analysis import prominence_pnc
from nucleus_analysis.phenotype import pixel_size
from nucleus_analysis.projection_cache import read_cached
from nucleus_analysis.review import ReviewSession

BASELINE = "f53cf62912b6188f7886af3c72a1689119888a0f"
STABLE = "d56e429a448ea8b95a70140260573391c36d7c12"
GROUPS = ("PNC negative", "PNC positive", "PNC small")
ABLATIONS = ("baseline", "no_fractional_noise_floor", "reference_min", "reference_local",
             "score_max", "support_quarter", "support_growth", "support_no_raw",
             "no_min_area", "no_max_area", "no_extent_gate", "no_boundary_gate",
             "no_candidate_penalty", "z_hard", "z_supporting")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def csv_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys or ["empty"])
        writer.writeheader()
        writer.writerows(rows)


def source_identity():
    root = Path(__file__).resolve().parents[1]
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    from nucleus_analysis import __version__

    return {"version": __version__, "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
            "files": {p.relative_to(root).as_posix(): sha(p) for folder in ("src/nucleus_analysis", "tools")
                      for p in sorted((root / folder).glob("*.py"))}}


def acquisition(path):
    import nd2

    with nd2.ND2File(path) as reader:
        channels = reader.metadata.channels
        text = reader.text_info
        description = text.get("description", "")
        blocks = re.split(r"Plane #\d+:\s*", description)[1:]
        settings = []
        for block in blocks:
            def number(pattern):
                match = re.search(pattern, block)
                return float(match[1]) if match else None
            settings.append({"name": (re.search(r"Name:\s*([^\r\n]+)", block)[1]
                                      if re.search(r"Name:\s*([^\r\n]+)", block) else None),
                             "exposure_ms": number(r"Exposure:\s*([\d.]+)\s*ms"),
                             "gain_x": number(r"Calibrated Gain:\s*([\d.]+)"),
                             "binning": (re.search(r"Binning:\s*([^\r\n]+)", block)[1]
                                         if re.search(r"Binning:\s*([^\r\n]+)", block) else None)})
        frame = reader.frame_metadata(0)
        marker = channels[1]
        signature = {"channels": [c.channel.name for c in channels], "camera": text.get("capturing", "").splitlines()[0],
                     "objective": text.get("optics"), "settings": settings,
                     "calibration": list(marker.volume.axesCalibration),
                     "significant_bits": reader.attributes.bitsPerComponentSignificant,
                     "projection": "maximum Z", "z_planes": reader.sizes.get("Z", 1)}
        # Z count affects incidental maxima; do not silently pool it for controls.
        key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        return {"signature": key, "compatibility": signature, "sizes": dict(reader.sizes),
                "date": text.get("date"), "stage": dataclasses.asdict(frame.channels[1].position),
                "specimen_id": None, "molecular_marker_identity": None,
                "separate_nucleolar_channel": False,
                "raw_size": Path(path).stat().st_size, "raw_mtime_ns": Path(path).stat().st_mtime_ns}


def plan(previous_split, output, seed=20261128):
    output = Path(output)
    if (output / "split.json").exists():
        raise ValueError("Do not overwrite an existing split")
    cases = json.loads(Path(previous_split).read_text(encoding="utf-8"))["cases"]
    for case in cases:
        case.pop("split")
        case["acquisition"] = acquisition(case["source"])
        case["unit"] = case["id"]  # All planes/time/position/nuclei of this ND2 stay together.
        case["raw_sha256"] = sha(case["source"])
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate projection pairs must be grouped before splitting")
    rng = np.random.default_rng(seed)
    forced = {("PNC negative", "IMG2.nd2"), ("PNC small", "IMG1.nd2"), ("PNC small", "IMG9.nd2")}
    for group in GROUPS:
        selected = sorted((c for c in cases if c["group"] == group), key=lambda c: c["id"])
        n_dev = int(np.floor(.6 * len(selected) + .5))
        known = [c for c in selected if (group, Path(c["source"]).name) in forced]
        remaining = [c for c in selected if c not in known]
        ids = {c["id"] for c in known}
        ids.update(remaining[i]["id"] for i in rng.permutation(len(remaining))[:n_dev-len(known)])
        for case in selected:
            case["split"] = "development" if case["id"] in ids else "validation"
    audit_ids = []
    for group in GROUPS:
        group_cases = sorted((c for c in cases if c["group"] == group and c["split"] == "development"), key=lambda c: c["id"])
        known = [c for c in group_cases if (group, Path(c["source"]).name) in forced]
        chosen = (known + [c for c in group_cases if c not in known])[:2]
        audit_ids.extend(c["id"] for c in chosen)
    protected = [Path("dist/preview/PNC-Counter-0.7.0.dev2-Preview-Setup-x64.exe"),
                 Path("dist/preview/build-info.json"), Path("dist/preview/SHA256SUMS.txt")]
    protected += [p for p in Path("validation/local/pnc-discrimination/v070-dev2").rglob("*")
                  if p.is_file() and "cache" not in p.parts and p.suffix in (".json", ".html", ".png")]
    document = {"schema": 1, "seed": seed, "development_fraction": .6, "cases": cases,
                "baseline": {"version": "0.7.0.dev2", "commit": BASELINE},
                "stable": {"version": "0.6.0", "commit": STABLE}, "source": source_identity(),
                "previous_split": {"path": str(Path(previous_split).resolve()), "sha256": sha(previous_split)},
                "unit": "one ND2 field acquisition; duplicate projection pairs prohibited",
                "group_assumptions": ["No specimen ID or related-field ID is supplied by metadata.",
                    "Stage X/Y=-1 are sentinel values, not evidence that fields are identical.",
                    "Shared capture dates/settings are batches, not proven independent specimens.",
                    "True specimen grouping is unavailable: all results are exploratory.",
                    "All fields have been examined previously; reshuffling does not create independence."],
                "audit_ids": audit_ids, "audit_design": "Two predefined development fields/group; each ablation changes one factor only.",
                "ablations": ABLATIONS, "audit_sensitivities": [25, 50, 75, 100],
                "protected_dev2": {str(p.resolve()): sha(p) for p in protected if p.exists()}}
    write(output / "split.json", document)
    counts = {g: {s: sum(c["group"] == g and c["split"] == s for c in cases)
                  for s in ("development", "validation")} for g in GROUPS}
    write(output / "metadata-summary.json", {"split_counts": counts,
          "marker_exposure_ms": {g: sorted({c["acquisition"]["compatibility"]["settings"][1]["exposure_ms"]
                                            for c in cases if c["group"] == g}) for g in GROUPS},
          "dates": {g: sorted({c["acquisition"]["date"].split()[0] for c in cases if c["group"] == g}) for g in GROUPS}})
    print(json.dumps(counts), flush=True)


def instrumented(ablation="baseline"):
    if ablation not in ABLATIONS:
        raise ValueError("Unknown one-factor ablation")
    raw = subprocess.check_output(["git", "show", BASELINE + ":src/nucleus_analysis/prominence_pnc.py"], text=True)
    code = raw[raw.index("def prepare_prominence("):raw.index("\ndef select_prominence(")]
    def edit(old, new):
        nonlocal code
        if old not in code:
            raise ValueError(f"Baseline instrumentation anchor changed: {old}")
        code = code.replace(old, new)
    edit("    image = np.asarray(image)", "    discarded = []\n    image = np.asarray(image)")
    edit("            if not anchor:\n                continue", """            if not anchor:
                discarded.append({"NucleusID": int(identifier), "SeedY": int(py+y0), "SeedX": int(px+x0),
                                  "Stage": "discarded: raw anchor absent", "PeakSNR": peak / floor,
                                  "ProposedSupportPixels": int(support.sum())})
                continue""")
    edit("            flags = []", "            pre_gate_score = float(signal)\n            flags = []")
    edit("            z_score, focus, best_z = None, None, None", "            pre_z_score = float(signal)\n            z_score, focus, best_z = None, None, None")
    edit("            nucleus_candidates.append((row, sy+y0, sx+x0))", """            row.update(SeedY=int(py+y0), SeedX=int(px+x0), NuclearReference=nuclear,
                       RingReference=float(np.median(reference)) if len(reference) else nuclear,
                       PeakResponse=peak, RawNoise=noise, LocalNoise=local_noise, ExtractionFloor=floor,
                       SmoothedSNR=peak/floor, MeanSupportIntensity=float(np.mean(values[sy,sx])),
                       PreGateScore=pre_gate_score, PreZScore=pre_z_score, PrePenaltyScore=float(signal))
            nucleus_candidates.append((row, sy+y0, sx+x0))""")
    edit("    return AdaptiveFeatures(score_image, measurements, labels, tuple(candidates))",
         "    return AdaptiveFeatures(score_image, measurements, labels, tuple(candidates)), discarded")
    if ablation == "no_fractional_noise_floor":
        edit(".02 * nuclear", "0. * nuclear")
        edit(".02 * abs(bg)", "0. * abs(bg)")
    elif ablation == "reference_min":
        edit("bg = max(nuclear,", "bg = min(nuclear,")
    elif ablation == "reference_local":
        edit("bg = max(nuclear, float(np.median(reference)))", "bg = float(np.median(reference))")
    elif ablation == "score_max":
        edit("signal = min(peak / floor, prominence / denominator)", "signal = max(peak / floor, prominence / denominator)")
    elif ablation == "support_quarter":
        edit("peak / 2", "peak / 4")
    elif ablation == "support_growth":
        edit("mask=mask & (normalized >= 1.5)", "mask=mask & (normalized >= .5)")
        edit("peak / 2", "peak / 4")
    elif ablation == "support_no_raw":
        edit("support &= values[region.slice] - local_background[region.slice] >= peak / 2", "support &= True")
    elif ablation == "no_min_area":
        edit("if area < 3:", "if area < 1:")
    elif ablation == "no_max_area":
        edit("if area > 500 or extent < .15:", "if extent < .15:")
    elif ablation == "no_extent_gate":
        edit("if area > 500 or extent < .15:", "if area > 500:")
    elif ablation == "no_boundary_gate":
        edit("            if boundary:\n                signal = 0.", "            if False:\n                signal = 0.")
    elif ablation == "no_candidate_penalty":
        edit("penalty = np.sqrt(1 + np.log1p(len(nucleus_candidates)))", "penalty = 1.")
    elif ablation == "z_supporting":
        edit("signal = min(signal, z_score) * np.sqrt(focus)", "signal = signal  # Z measurements only")
        edit("                    if same.sum() < 3:", "                    if False:")
        edit("                else:\n                    signal = 0.", "                else:\n                    pass")
    namespace = dict(prominence_pnc.__dict__)
    exec(compile(code, f"<dev2 loss audit: {ablation}>", "exec"), namespace)
    return namespace["prepare_prominence"]


def load_case(case):
    directory = Path(case["directory"])
    for name, expected in case["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Frozen export changed: " + str(directory / name))
    session = ReviewSession.open(directory)
    _, details = session.counts()
    ids = sorted(i for i in session.masks if not details[i]["rejected"])
    masks = [session.masks[i].pixels for i in ids]
    return session, ids, masks


def audit(output):
    output = Path(output)
    if (output / "audit/summary.json").exists():
        raise ValueError("Audit already exists; preserve it")
    split = json.loads((output / "split.json").read_text(encoding="utf-8"))
    candidates, fields, nuclei = [], [], []
    funcs = {a: instrumented(a) for a in ABLATIONS}
    for case in split["cases"]:
        if case["split"] != "development":
            continue
        session, ids, masks = load_case(case)
        p = session.projections
        calibration = pixel_size(session.config, p.metadata)
        methods = ABLATIONS if case["id"] in split["audit_ids"] else ("baseline",)
        evidence = {}
        if len(methods) > 1:
            config = dataclasses.replace(session.config, pnc_mode="prominence", pnc_z_policy="auto")
            raw = read_cached(case["source"], config, cache=output / "cache")
            if not np.array_equal(raw.pnc_max, p.pnc_max):
                raise ValueError("Raw projection differs from frozen export")
            evidence = raw.pnc_evidence
        for method in methods:
            started = time.perf_counter()
            features, discarded = funcs[method](p.pnc_max, masks, ids, calibration, 3,
                evidence=evidence if method.startswith("z_") else {},
                z_policy="auto" if method.startswith("z_") else "projection")
            elapsed = time.perf_counter() - started
            if method == "baseline":
                original = prominence_pnc.prepare_prominence(p.pnc_max, masks, ids, calibration, 3, z_policy="projection")
                np.testing.assert_array_equal(features.labels, original.labels)
                for measured, expected in zip(features.candidates, original.candidates):
                    for key, value in expected.items():
                        assert measured[key] == value, (key, measured[key], value)
                assert len(features.candidates) == len(original.candidates)
            common = {"field": case["id"], "group": case["group"], "source": case["source"],
                      "ablation": method, "version": "0.7.0.dev2", "baseline_commit": BASELINE}
            candidates.extend({**common, **row, "Stage": "scored"} for row in features.candidates)
            candidates.extend({**common, **row} for row in discarded)
            for sensitivity in split["audit_sensitivities"]:
                cutoff = prominence_pnc.sensitivity_threshold(sensitivity)
                accepted = []
                reasons = Counter()
                for identifier in ids:
                    rows = [c for c in features.candidates if c["NucleusID"] == identifier]
                    lost = [c for c in discarded if c["NucleusID"] == identifier]
                    usable = [c for c in rows if (1 if method == "no_min_area" else 3) <= c["Area"] <= (10**9 if method == "no_max_area" else 500)]
                    call = any(c["SignalScore"] >= cutoff for c in usable)
                    if call:
                        reason = "accepted"
                    elif not rows:
                        reason = "support anchor discarded" if lost else "no extracted seed"
                    elif any(c["PreGateScore"] >= cutoff and c["SignalScore"] == 0 for c in rows):
                        reason = "hard rule suppressed score above cutoff"
                    elif any(c["PrePenaltyScore"] >= cutoff and c["SignalScore"] < cutoff for c in usable):
                        reason = "candidate count penalty crossed cutoff"
                    elif any(c["SignalScore"] >= cutoff for c in rows):
                        reason = "selection area gate"
                    else:
                        reason = "candidate low-scored (may also have hard gates)"
                    reasons[reason] += 1
                    accepted.append(call)
                    nuclei.append({**common, "MaskID": identifier, "sensitivity": sensitivity,
                                   "positive": int(call), "candidates": len(rows), "discarded_anchors": len(lost),
                                   "zero_scored": sum(c["SignalScore"] == 0 for c in rows), "classification": reason})
                fields.append({**common, "sensitivity": sensitivity, "positive": sum(accepted), "total": len(ids),
                               "retained": len(session.masks), "excluded": len(session.masks)-len(ids),
                               "candidates": len(features.candidates), "discarded_anchors": len(discarded),
                               "seconds": elapsed, "attrition": dict(reasons)})
            print(f"audit {case['group']} {Path(case['source']).name} {method}: {elapsed:.2f}s", flush=True)
    csv_rows(output / "audit/candidates.csv", candidates)
    csv_rows(output / "audit/nuclei.csv", nuclei)
    csv_rows(output / "audit/fields.csv", fields)
    write(output / "audit/summary.json", {"source": source_identity(), "baseline_parity_checked": True,
          "audit_ids": split["audit_ids"], "fields": fields,
          "limits": "Classifications locate numerical losses, not reviewed visible-focus misses or biological errors."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "audit"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--previous-split", type=Path)
    args = parser.parse_args()
    if args.stage == "plan":
        plan(args.previous_split, args.output)
    else:
        audit(args.output)


if __name__ == "__main__":
    main()
