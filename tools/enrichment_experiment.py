"""Bounded BEFORE dev2 / AFTER dev3 experiment. Run as python -m tools.enrichment_experiment.

The audit and split precede the new comparison. Development selects operating
points; immutable frozen settings and control profiles precede validation.
All predeclared diagnostic curves are reported; validation cannot reselect.
"""

import argparse
import ast
import gzip
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

from nucleus_analysis.adaptive_pnc import prepare_adaptive, select_adaptive
from nucleus_analysis.control_profile import compatible_floor, fit_profiles
from nucleus_analysis.enrichment_pnc import (
    ALGORITHM,
    MAPPING,
    PARAMETERS,
    prepare_enrichment,
    select_enrichment,
)
from nucleus_analysis.phenotype import assign_spots, pixel_size
from nucleus_analysis.projection_cache import read_cached
from nucleus_analysis.prominence_pnc import prepare_prominence, select_prominence
from tools.pnc_loss_audit import (
    BASELINE,
    GROUPS,
    STABLE,
    csv_rows,
    load_case,
    sha,
    source_identity,
    write,
)

LEVELS = (25., 50., 75., 100.)
AFTER = ("A-half", "A-growth", "B-optional-control", "C-mixture")


def stable_threshold():
    code = subprocess.check_output(["git", "show", STABLE + ":src/nucleus_analysis/pipeline.py"], text=True)
    function = next(n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef) and n.name == "threshold_pnc")
    namespace = {"np": np, "ndi": ndi}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<stable v0.6.0 threshold_pnc>", "exec"), namespace)
    return namespace["threshold_pnc"]


def baseline_unchanged():
    # Compare exact Git blobs after CRLF normalization, never import a mutated baseline.
    for relative in ("src/nucleus_analysis/prominence_pnc.py", "src/nucleus_analysis/adaptive_pnc.py",
                     "src/nucleus_analysis/phenotype.py", "src/nucleus_analysis/pnc_evidence.py"):
        before = subprocess.check_output(["git", "show", BASELINE + ":" + relative]).replace(b"\r\n", b"\n")
        if Path(relative).read_bytes().replace(b"\r\n", b"\n") != before:
            raise ValueError("Baseline implementation changed: " + relative)


def plan(output):
    output = Path(output)
    if (output / "comparison-plan.json").exists():
        raise ValueError("Comparison plan already exists")
    if not (output / "audit/summary.json").exists():
        raise ValueError("Complete the loss audit before planning a detector comparison")
    identity = source_identity()
    if identity["dirty"]:
        raise ValueError("Commit source before declaring the comparison")
    baseline_unchanged()
    write(output / "comparison-plan.json", {"schema": 1, "source": identity,
          "split_sha256": sha(output / "split.json"), "audit_sha256": sha(output / "audit/summary.json"),
          "before": {"stable_version": "0.6.0", "stable_commit": STABLE,
                     "preview_version": "0.7.0.dev2", "preview_commit": BASELINE},
          "after_version": "0.7.0.dev3", "algorithm": ALGORITHM, "mapping": MAPPING,
          "parameters": PARAMETERS, "sensitivity_grid": LEVELS, "after_methods": AFTER,
          "before_methods": ["stable-legacy", "dev2-adaptive", "dev2-prominence"],
          "baseline_default": {"threshold_mode": "local", "image_threshold": 90, "neighborhood_size": 21,
                               "positive_threshold": 10, "adaptive_sensitivity": 50, "prominence_sensitivity": 50,
                               "rejected_frozen_prominence_sensitivity": 25, "spot_area": [3, 500], "distance": 3},
          "calibration": {"minimum_matching_development_fields": 2, "field_quantile": .95,
                          "exact_match_includes": ["channels", "exposure", "gain", "binning", "objective", "scale", "Z count"],
                          "fallback": "uncalibrated A-growth; always report coverage"},
          "mixture": {"algorithm": "one-two-intensity-gaussian-bic-v1", "bic_margin": 10, "max_samples": 1024,
                      "max_iterations": 80, "starts": [.01, .1, .3], "fallback": "no mixture-derived signal"},
          "operating_point_selection": "Among the four declared sensitivities, minimize normalized shortfall below "
               "85% of legacy positive field mean and 100% of legacy small field mean; then minimize negative field mean. "
               "Freeze independently for each method. Never select on validation.",
          "proxy_screen": "Negative mean <=70% legacy AND positive mean >=85% legacy AND small mean >=legacy. "
                          "This is diagnostic, never biological accuracy or proof of visible preservation.",
          "validation": "Evaluate every declared fixed curve point for transparency; mark the development-frozen point. No reselection.",
          "manual_calls": "Evaluate automatic calls separately; preserve and export overrides/effective calls. Exclude overrides from control fitting.",
          "z": "Supporting measurements on the six audit fields; no Z scoring or morphology veto in A/B/C.",
          "promotion": "No default/UI/installer change without visual biological evaluation and owner approval."})


def check_plan(output):
    spec = json.loads((output / "comparison-plan.json").read_text(encoding="utf-8"))
    if sha(output / "split.json") != spec["split_sha256"]:
        raise ValueError("Split changed after declaration")
    current = source_identity()
    if current["dirty"] or current["files"] != spec["source"]["files"]:
        raise ValueError("Source changed after declaration; create a new declared experiment")
    baseline_unchanged()
    return spec


def signal_protocol(spec):
    return {"algorithm": spec["algorithm"], "parameters": spec["parameters"], "support": "growth",
            "scoring_source_sha256": spec["source"]["files"]["src/nucleus_analysis/enrichment_pnc.py"],
            "selection": [0, 1, 0, 0], "min_distance": 3}


def aggregate(rows):
    result = {}
    for group in GROUPS:
        fields = [r for r in rows if r["group"] == group]
        rates = [100*r["automatic_positive"]/r["total"] for r in fields if r["total"]]
        n = sum(r["total"] for r in fields)
        pos = sum(r["automatic_positive"] for r in fields)
        result[group] = {"fields": len(fields), "positive": pos, "total": n,
                        "excluded": sum(r["excluded"] for r in fields),
                        "manual_overrides": sum(r["manual_overrides"] for r in fields),
                        "field_mean": float(np.mean(rates)) if rates else None,
                        "pooled_percent": 100*pos/n if n else None,
                        "distribution_min_q25_median_q75_max": list(map(float, np.percentile(rates, [0,25,50,75,100]))) if rates else []}
    return result


def select_operating_points(rows):
    # This function receives development rows only; a validation row is an error.
    if any(r["split"] != "development" for r in rows):
        raise ValueError("Operating-point selection cannot read validation fields")
    legacy = aggregate([r for r in rows if r["method"] == "stable-legacy"])
    bn, bp, bs = [legacy[g]["field_mean"] for g in GROUPS]
    frozen = {}
    for method in AFTER:
        options = []
        for level in LEVELS:
            summary = aggregate([r for r in rows if r["method"] == method and r["sensitivity"] == level])
            n, p, s = [summary[g]["field_mean"] for g in GROUPS]
            violation = max(0, .85*bp-p)/max(.85*bp, 1) + max(0, bs-s)/max(bs, 1)
            options.append((violation, n, level, n <= .7*bn and p >= .85*bp and s >= bs))
        violation, n, level, passed = min(options, key=lambda o: (o[0], o[1], o[2]))
        frozen[method] = {"sensitivity": level, "proxy_screen_passed": bool(passed),
                          "normalized_preservation_shortfall": violation, "development_negative_field_mean": n,
                          "adopted_as_default": False}
    return frozen


def save_features(output, case, session, features):
    folder = output / "features"
    folder.mkdir(exist_ok=True)
    np.savez_compressed(folder / (case["id"] + ".npz"), **{name: f.labels for name, f in features.items()})
    data = {"case": case, "config": session.config.to_dict(),
            "nuclei": {str(i): {"pixels": len(m.pixels), "rejected": m.rejected, "override": m.pnc_override}
                        for i, m in session.masks.items()},
            "features": {name: {"measurements": f.measurements, "candidates": f.candidates}
                         for name, f in features.items()}}
    with gzip.open(folder / (case["id"] + ".json.gz"), "wt", encoding="utf-8") as handle:
        json.dump(data, handle, allow_nan=False)


def evaluate(output, case, session, ids, masks, method, level, selected, *, seconds, calibration_status="not requested"):
    nucleus_rows = [{"MaskID": i, "Area": len(p), "BadMask": 0} for i, p in zip(ids, masks)]
    if method == "stable-legacy":
        call_by_id = selected
    else:
        counts = assign_spots(nucleus_rows, masks, selected)
        call_by_id = {i: counts[i] >= 1 for i in ids}
    records = []
    for i in ids:
        override = session.masks[i].pnc_override
        automatic = bool(call_by_id[i])
        records.append({"field": case["id"], "group": case["group"], "split": case["split"],
                        "method": method, "sensitivity": level, "MaskID": i,
                        "automatic_positive": int(automatic), "manual_override": "auto" if override is None else int(override),
                        "effective_positive": int(automatic if override is None else override)})
    field = {"field": case["id"], "source": case["source"], "group": case["group"], "split": case["split"],
             "method": method, "sensitivity": level,
             "version": "0.6.0" if method == "stable-legacy" else "0.7.0.dev2" if method.startswith("dev2-") else "0.7.0.dev3",
             "automatic_positive": sum(r["automatic_positive"] for r in records),
             "effective_positive": sum(r["effective_positive"] for r in records),
             "total": len(ids), "retained": len(session.masks), "excluded": len(session.masks)-len(ids),
             "manual_overrides": sum(session.masks[i].pnc_override is not None for i in ids),
             "preparation_seconds": seconds, "calibration_status": calibration_status}
    return field, records


def run(output, phase):
    output = Path(output)
    spec = check_plan(output)
    if (output / (phase + ".json")).exists():
        raise ValueError("Completed phase is immutable")
    split = json.loads((output / "split.json").read_text(encoding="utf-8"))
    cases = [c for c in split["cases"] if c["split"] == phase]
    if phase == "validation":
        frozen = json.loads((output / "frozen.json").read_text(encoding="utf-8"))
        if sha(output / "development.json") != frozen["development_sha256"] or sha(output / "control-profiles.json") != frozen["control_profiles_sha256"]:
            raise ValueError("Frozen development results or control profiles changed")
        profile = json.loads((output / "control-profiles.json").read_text(encoding="utf-8"))
    else:
        profile = None
    fields, nuclei, runtime, controls, pending = [], [], [], [], []
    legacy = stable_threshold()
    protocol = signal_protocol(spec)
    for case in cases:
        raw_stat = Path(case["source"]).stat()
        if (raw_stat.st_size != case["acquisition"]["raw_size"]
                or raw_stat.st_mtime_ns != case["acquisition"]["raw_mtime_ns"]):
            raise ValueError("Raw acquisition changed since the split inventory")
        loaded = time.perf_counter()
        session, ids, masks = load_case(case)
        load_seconds = time.perf_counter()-loaded
        p = session.projections
        calibration = pixel_size(session.config, p.metadata)
        options = {"dapi_channel": 0, "pnc_channel": 1, "time_index": 0, "position_index": 0}
        if any(getattr(session.config, k) != v for k, v in options.items()):
            raise ValueError("Acquisition selection differs from declared protocol")
        evidence = {}
        z_seconds = 0.
        if case["id"] in split["audit_ids"]:
            z_started = time.perf_counter()
            raw = read_cached(case["source"], replace(session.config, pnc_mode="prominence", pnc_z_policy="auto"), cache=output / "cache")
            if not np.array_equal(raw.pnc_max, p.pnc_max):
                raise ValueError("Raw marker projection differs from the frozen analysis")
            evidence = raw.pnc_evidence
            z_seconds = time.perf_counter()-z_started
        baseline_config = replace(session.config, threshold_mode="local", image_threshold=90., neighborhood_size=21, positive_threshold=10)
        started = time.perf_counter()
        fg = legacy(p.pnc_max, baseline_config).ravel()
        calls = {i: fg[idx].sum() >= 10 for i, idx in zip(ids, masks)}
        row, cells = evaluate(output, case, session, ids, masks, "stable-legacy", None, calls, seconds=time.perf_counter()-started)
        fields.append(row)
        nuclei.extend(cells)
        prepared = {}
        timings = {"field": case["id"], "split": phase, "group": case["group"], "shape": list(p.pnc_max.shape),
                   "projection_load_seconds": load_seconds, "z_evidence_read_seconds": z_seconds,
                   "condition": "first feature preparation in process; exported projections read from disk; OS cache uncontrolled"}
        for method, prepare, select, kwargs in (
            ("dev2-adaptive", prepare_adaptive, select_adaptive, {}),
            ("dev2-prominence", prepare_prominence, select_prominence, {"z_policy": "projection"}),
            ("A-half", prepare_enrichment, select_enrichment, {"support": "half", "evidence": evidence}),
            ("A-growth", prepare_enrichment, select_enrichment, {"support": "growth", "evidence": evidence}),
            ("C-mixture", prepare_enrichment, select_enrichment, {"support": "growth", "evidence": evidence, "mixture": True})):
            started = time.perf_counter()
            f = prepare(p.pnc_max, masks, ids, calibration, 3, **kwargs)
            elapsed = time.perf_counter()-started
            timings[method + "_seconds"] = elapsed
            prepared[method] = f
            for level in LEVELS:
                _, _, spots = select(f, level, **({"mixture": True} if method == "C-mixture" else {}))
                row, cells = evaluate(output, case, session, ids, masks, method, level, spots, seconds=elapsed)
                fields.append(row)
                nuclei.extend(cells)
        np.testing.assert_array_equal(prepared["A-growth"].labels, prepared["C-mixture"].labels)
        save_features(output, case, session, prepared)
        maxima = {i: prepared["A-growth"].measurements[i]["max_score"] for i in ids}
        pending.append((case, session.config.to_dict(), ids, maxima))
        if phase == "development" and case["group"] == "PNC negative":
            controls.append({"split": phase, "role": "negative_control", "field": case["id"],
                "source_sha256": case["raw_sha256"], "acquisition_signature": case["acquisition"]["signature"],
                "automatic_nucleus_maxima": [maxima[i] for i in ids if session.masks[i].pnc_override is None]})
        runtime.append(timings)
        print(f"{phase} {case['group']} {Path(case['source']).name}: A growth {timings['A-growth_seconds']:.3f}s", flush=True)
    if profile is None:
        profile = fit_profiles(controls, protocol)
        write(output / "control-profiles.json", profile)
    # B uses cached scalar maxima; never reads validation controls or refits.
    for case, config, ids, maxima in pending:
        floor, status = compatible_floor(profile, case["acquisition"]["signature"], protocol)
        source_rows = [r for r in fields if r["field"] == case["id"] and r["method"] == "A-growth"]
        for old in source_rows:
            from nucleus_analysis.enrichment_pnc import sensitivity_threshold

            cutoff = max(sensitivity_threshold(old["sensitivity"]), floor or 0.)
            old_cells = [r for r in nuclei if r["field"] == case["id"] and r["method"] == "A-growth" and r["sensitivity"] == old["sensitivity"]]
            cells = [{**r, "method": "B-optional-control", "automatic_positive": int(maxima[r["MaskID"]] >= cutoff),
                      "effective_positive": int(maxima[r["MaskID"]] >= cutoff) if r["manual_override"] == "auto" else r["manual_override"]} for r in old_cells]
            fields.append({**old, "method": "B-optional-control", "automatic_positive": sum(r["automatic_positive"] for r in cells),
                           "effective_positive": sum(r["effective_positive"] for r in cells), "calibration_status": status})
            nuclei.extend(cells)
    summary = {"stable-legacy": aggregate([r for r in fields if r["method"] == "stable-legacy"])}
    for method in ("dev2-adaptive", "dev2-prominence", *AFTER):
        for level in LEVELS:
            summary[f"{method}@{level:g}"] = aggregate([r for r in fields if r["method"] == method and r["sensitivity"] == level])
    write(output / (phase + ".json"), {"source": source_identity(), "plan_sha256": sha(output / "comparison-plan.json"),
          "fields": fields, "summary": summary, "runtime": runtime,
          "profile_coverage": {g: {"compatible": sum(not r["calibration_status"].startswith("fallback") for r in fields
                                                      if r["group"] == g and r["method"] == "B-optional-control" and r["sensitivity"] == 50),
                                    "fields": sum(c["group"] == g for c in cases)} for g in GROUPS}})
    csv_rows(output / (phase + "-fields.csv"), fields)
    csv_rows(output / (phase + "-nuclei.csv"), nuclei)
    if phase == "development":
        write(output / "frozen.json", {"source": source_identity(), "selected": select_operating_points(fields),
              "development_sha256": sha(output / "development.json"),
              "control_profiles_sha256": sha(output / "control-profiles.json"),
              "validation_used": False, "default_changed": False,
              "note": "All declared curve points will be displayed. Frozen operating points cannot be reselected after validation."})
    print(json.dumps({k: {g: v["field_mean"] for g,v in row.items()} for k,row in summary.items()}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "development", "validation"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.stage == "plan":
        plan(args.output)
    else:
        run(args.output, args.stage)


if __name__ == "__main__":
    main()
