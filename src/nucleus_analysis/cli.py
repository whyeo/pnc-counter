"""Batch CLI with explicit settings, mask replay, and cache provenance."""

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from .config import AnalysisConfig
from .output import export_result, write_csv
from .phenotype import segmentation_config
from .pipeline import analyze
from .projection_cache import read_cached
from .segmentation import Segmenter, cache_fingerprint, file_sha256, load_masks, save_masks


def build_parser():
    parser = argparse.ArgumentParser(description="Segment nuclei and count PNC-positive nuclei")
    parser.add_argument("input", nargs="?", type=Path, help="ND2/TIFF file or folder")
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--config", type=Path, help="Import settings JSON")
    parser.add_argument("--save-config", type=Path, help="Export effective settings JSON")
    parser.add_argument("--gui", action="store_true", help="Open the desktop app")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--axes", help="Explicit TIFF axes, e.g. ZCYX (ND2 uses metadata)")
    parser.add_argument("--masks", type=Path, help="Replay .npz or MATLAB segmentation .mat (single input)")
    parser.add_argument("--cache", type=Path, help="Cache candidate masks; thresholds can then change cheaply")
    choices = {"backend": ["sam2", "sam3", "watershed"], "threshold_mode": ["local", "global"],
               "quality_filter": ["none", "legacy-svm"], "sam2_model": ["tiny", "small", "base_plus", "large"],
               "device": ["cpu", "cuda", "mps"], "border_policy": ["include", "exclude"],
               "pnc_mode": ["pixels", "spots", "adaptive", "prominence", "enrichment"],
               "pnc_z_policy": ["auto", "projection"]}
    types = {"min_nucleus_area": int, "max_nucleus_area": int, "positive_threshold": int,
             "image_threshold": float, "pnc_sensitivity": float, "pnc_enrichment_threshold": float,
             "neighborhood_size": int, "dapi_channel": int,
             "pnc_channel": int, "time_index": int, "position_index": int,
             "overlap_threshold": float, "checkpoint": str, "points_per_side": int,
             "points_per_batch": int, "score_threshold": float, "stability_threshold": float,
             "watershed_min_distance": int, "watershed_sigma": float, "sam3_prompt": str,
             "min_nucleus_area_um2": float, "max_nucleus_area_um2": float,
             "pixel_size_x_um": float, "pixel_size_y_um": float, "border_margin": int,
             "min_spot_count": int, "spot_min_area": int, "spot_max_area": int,
             "spot_min_distance": int, "spot_background_sigma": float, "review_positive_margin": int}
    for name, allowed in choices.items():
        parser.add_argument("--" + name.replace("_", "-"), choices=allowed)
    for name, kind in types.items():
        parser.add_argument("--" + name.replace("_", "-"), type=kind)
    return parser


def discover_inputs(path, recursive=False):
    if path.is_file():
        if path.suffix.lower() not in (".nd2", ".tif", ".tiff"):
            raise ValueError("Input must be an ND2 or TIFF image")
        return [path]
    if not path.is_dir():
        raise ValueError(f"Input does not exist: {path}")
    iterator = path.rglob("*") if recursive else path.iterdir()
    paths = sorted(p for p in iterator if p.is_file() and p.suffix.lower() in (".nd2", ".tif", ".tiff"))
    if not paths:
        raise ValueError("No ND2/TIFF images found")
    return paths


def run_batch(paths, config, output, *, axes=None, masks_path=None, cache=None,
              progress=None, cancelled=None, stage_progress=None, config_for_path=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    segmenter = Segmenter(config)
    summary = []
    errors = []
    for path in paths:
        if cancelled and cancelled():
            break
        path = Path(path)
        # Distinguish same-named files from different folders and extensions.
        identifier = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:10]
        destination = output / f"{path.stem}-{identifier}"
        current = config_for_path(path) if config_for_path else config

        def stage(name):
            if stage_progress:
                stage_progress(path, name)

        try:
            stage("Loading image")
            projections = read_cached(path, current, axes=axes, cache=cache)
            effective = segmentation_config(current, projections.metadata)
            segmenter.config = effective
            candidates = None
            provenance = {"kind": "generated", "backend": current.backend}
            stage("Finding nuclei")
            if masks_path:
                candidates = load_masks(masks_path, projections.dapi_max.shape)
                provenance = {"kind": "imported", "path": str(Path(masks_path).resolve()),
                              "sha256": file_sha256(masks_path)}
            elif cache:
                fingerprint = cache_fingerprint(projections.dapi_max, effective)
                cache_file = Path(cache) / f"{fingerprint}.npz"
                if cache_file.is_file():
                    with np.load(cache_file, allow_pickle=False) as data:
                        if str(data["fingerprint"]) != fingerprint:
                            raise ValueError("Cache fingerprint does not match")
                    candidates = load_masks(cache_file, projections.dapi_max.shape)
                else:
                    candidates = segmenter.generate(projections.dapi_max)
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    save_masks(cache_file, candidates, projections.dapi_max.shape, fingerprint)
                provenance.update(fingerprint=fingerprint, cache=str(cache_file.resolve()))
            if candidates is None:
                candidates = segmenter.generate(projections.dapi_max)
            stage("Measuring PNC")
            result = analyze(projections, current, masks=candidates, segmenter=segmenter)
            if not masks_path and current.checkpoint and current.backend.startswith("sam"):
                provenance["checkpoint_sha256"] = file_sha256(current.checkpoint)
            stage("Saving results")
            export_result(result, destination, provenance=provenance)
            row = {"Filename": str(path), **result.basic_stats, "Output": str(destination)}
            summary.append(row)
            stage("Done")
            if progress:
                progress(path, result.basic_stats, destination, None)
        except Exception as exc:
            stage("Error")
            errors.append({"Filename": str(path), "error": f"{type(exc).__name__}: {exc}"})
            if progress:
                progress(path, None, None, str(exc))
        # Persist completed work after every image, including partial/cancelled batches.
        write_csv(output / "summary.csv", summary,
                  ["Filename", "percentage", "n_negative", "n_positive", "n_bad", "n_total", "n_masks", "Output"])
        (output / "errors.json").write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    return summary, errors


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.gui:
        from .desktop_launcher import main as gui_main

        gui_main([])
        return 0
    try:
        config = AnalysisConfig.load(args.config) if args.config else AnalysisConfig()
        overrides = {name: getattr(args, name) for name in config.to_dict()
                     if getattr(args, name, None) is not None}
        config = replace(config, **overrides)
        if args.save_config:
            config.save(args.save_config)
        if args.input is None:
            if args.save_config:
                return 0
            parser.error("an input path or --gui is required")
        paths = discover_inputs(args.input, args.recursive)
        if args.masks and len(paths) != 1:
            raise ValueError("--masks can only be used with a single input image")

        def report(path, stats, destination, error):
            if error:
                print(f"ERROR {path}: {error}", file=sys.stderr)
            else:
                percent = f"{stats['percentage']:.2f}%" if stats["percentage"] is not None else "N/A"
                print(f"{path.name}: {stats['n_positive']} / {stats['n_total']} PNC+ ({percent})", flush=True)

        _, errors = run_batch(paths, config, args.output, axes=args.axes, masks_path=args.masks,
                              cache=args.cache, progress=report)
        return 1 if errors else 0
    except (ValueError, OSError, TypeError) as exc:
        parser.error(str(exc))
