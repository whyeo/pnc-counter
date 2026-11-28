"""Portable CSV/JSON/NPZ outputs and inspection overlays without matplotlib."""

import csv
import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from skimage.segmentation import find_boundaries

from .imaging import scale_uint8
from .segmentation import save_masks

STAT_COLUMNS = ["MaskID", "Area", "Smoothness", "PercentileIntensity_IQR",
                "PercentileIntensity_Mean", "PercentileIntensity_Std", "MeanIntensity_IQR",
                "MeanIntensity_Mean", "MeanIntensity_Std", "MaxIntensity_IQR", "MaxIntensity_Mean",
                "MaxIntensity_Std", "CentroidX", "CentroidY", "Circularity", "Eccentricity",
                "Solidity", "NumberCh2PixelsPositive", "BadMask", "Positive"]


def write_csv(path, rows, columns):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def overlay(result):
    base = np.repeat(result.images["ch1_max"][..., None], 3, axis=-1)
    colors = (("mask_negative", (255, 153, 179)), ("mask_positive", (100, 160, 255)),
              ("mask_bad", (180, 180, 180)))
    for name, color in colors:
        labels = result.images[name]
        active = labels > 0
        base[active] = (base[active] * 0.55 + np.array(color) * 0.45).astype(np.uint8)
        base[find_boundaries(labels, mode="inner")] = color
    if result.masks is not None:
        flagged = np.zeros(result.images["ch1_max"].shape, dtype=np.uint32)
        for row, idx in zip(result.full_stats, result.masks):
            if row.get("ReviewFlag"):
                flagged.ravel()[idx] = row["MaskID"]
        base[find_boundaries(flagged, mode="inner")] = (255, 220, 20)
    image = Image.fromarray(base)
    draw = ImageDraw.Draw(image)
    for row in result.full_stats:
        draw.text((row["CentroidX"] - 1, row["CentroidY"] - 1), str(row["MaskID"]),
                  fill="white", anchor="mm")
    return image


def visualization(result):
    """Four panels: DAPI, numbered masks, raw PNC, thresholded PNC."""
    h, w = result.images["ch1_max"].shape
    panels = [Image.fromarray(result.images["ch1_max"]).convert("RGB"), overlay(result),
              Image.fromarray(scale_uint8(result.images["ch2"])).convert("RGB"),
              Image.fromarray(result.images["ch2_thresh"].astype(np.uint8) * 255).convert("RGB")]
    if result.config.pnc_mode in ("spots", "adaptive", "prominence", "enrichment"):
        draw_spots = ImageDraw.Draw(panels[3])
        for spot in result.spots or []:
            x, y = spot["CentroidX"] - 1, spot["CentroidY"] - 1
            draw_spots.ellipse((x - 4, y - 4, x + 4, y + 4), outline=(40, 255, 100), width=2)
    canvas = Image.new("RGB", (w * 2, (h + 26) * 2), "#151820")
    draw = ImageDraw.Draw(canvas)
    for i, (panel, title) in enumerate(zip(panels, ["DAPI", "Nuclei: blue positive / pink negative / gray rejected / yellow flagged",
                                                 "PNC signal", "PNC positive pixels"])):
        x, y = (i % 2) * w, (i // 2) * (h + 26)
        draw.text((x + 8, y + 6), title, fill="white")
        canvas.paste(panel, (x, y + 26))
    return canvas


def export_result(result, directory, *, provenance=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    extra_columns = list(dict.fromkeys(key for row in result.full_stats for key in row
                                      if key not in STAT_COLUMNS))
    write_csv(directory / "nuclei.csv", result.full_stats, STAT_COLUMNS + extra_columns)
    from . import __version__

    app_version = __version__
    metadata = {"version": app_version, "created_utc": datetime.now(timezone.utc).isoformat(),
                "summary": result.basic_stats,
                "config": result.config.to_dict(), "input": result.metadata,
                "segmentation": provenance or {"kind": "generated", "backend": result.config.backend},
                "centroid_coordinates": "one-based X/Y pixels, matching MATLAB"}
    if result.config.pnc_mode == "adaptive":
        from .adaptive_pnc import ALGORITHM, sensitivity_threshold

        metadata["pnc_detection"] = {"algorithm": ALGORITHM, "sensitivity": result.config.pnc_sensitivity,
                                     "candidate_score_threshold": sensitivity_threshold(result.config.pnc_sensitivity),
                                     "score_units": "robust intranuclear noise units; not a probability",
                                     "candidate_support": "fixed half-height connected region",
                                     "validation_status": "experimental; requires reviewed controls"}
    if result.config.pnc_mode == "prominence":
        from .phenotype import pixel_size
        from .prominence_pnc import ALGORITHM, MAPPING, sensitivity_threshold

        metadata["pnc_detection"] = {
            "algorithm": ALGORITHM, "sensitivity": result.config.pnc_sensitivity,
            "sensitivity_mapping": MAPPING,
            "candidate_score_threshold": sensitivity_threshold(result.config.pnc_sensitivity),
            "score_units": "detector score; not a probability",
            "noise_floor": "max(robust noise, 2% background, 1e-6 image peak)",
            "candidate_support": "fixed half-prominence region with raw spatial support",
            "multiplicity": "divide by sqrt(1 + log1p(candidate count per nucleus))",
            "scales_um": [.10, .20, .40], "background_scale_um": 1.5,
            "pixel_scale_fallback": [.75, 1.5, 3.], "background_fallback": 10.,
            "pixel_size_um": pixel_size(result.config, result.metadata),
            "z_policy": result.config.pnc_z_policy,
            "evidence": result.metadata.get("pnc_evidence") if "pnc_z_score" in result.images else None,
            "effective_evidence": "per-plane local prominence" if "pnc_z_score" in result.images and result.config.pnc_z_policy == "auto"
                                  else "2D projection fallback; no Z evidence used",
            "validation_status": "experimental; biological separation not established"}
    if result.config.pnc_mode == "enrichment":
        from .local_enrichment import ALGORITHM

        metadata["pnc_detection"] = {
            "algorithm": ALGORITHM, "local_enrichment_threshold": result.config.pnc_enrichment_threshold,
            "score_units": "raw3x3 median / local reference median; not a probability",
            "reference": "eroded in-nucleus annulus12-20 small-sigma units; >=64pixels",
            "candidate_support": "fixed growth proposal geometry; stored area >=3pixels",
            "aggregation": "at least one eligible candidate reaches threshold",
            "reference_variation": "descriptive MAD, not calibrated instrument noise",
            "review": "human vetting required; quality warnings retained"}
    metadata["dependencies"] = {}
    for package in ("numpy", "scipy", "scikit-image", "nd2", "tifffile", "Pillow",
                    "torch", "torchvision", "SAM-2", "sam3"):
        try:
            metadata["dependencies"][package] = version(package)
        except PackageNotFoundError:
            pass
    (directory / "analysis.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    np.savez_compressed(directory / "images.npz", **result.images)
    if result.masks is not None:
        save_masks(directory / "nuclei_masks.npz", result.masks, result.images["ch1_max"].shape)
    if result.config.pnc_mode in ("spots", "adaptive", "prominence", "enrichment"):
        columns = ["SpotID", "Area", "CentroidX", "CentroidY", "AnchorPixel", "NucleusID"]
        columns += list(dict.fromkeys(key for row in result.spots or [] for key in row if key not in columns))
        write_csv(directory / "spots.csv", result.spots or [],
                  columns)
    if result.candidates is not None:
        columns = list(dict.fromkeys(k for row in result.candidates for k in row))
        write_csv(directory / "pnc_candidates.csv", result.candidates, columns or ["SpotID", "SignalScore"])
    visualization(result).save(directory / "visualization.png")
