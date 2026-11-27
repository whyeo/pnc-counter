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
    if result.config.pnc_mode == "spots":
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
    try:
        app_version = version("nucleus-analysis")
    except PackageNotFoundError:
        from . import __version__

        app_version = __version__ + "+source"
    metadata = {"version": app_version, "created_utc": datetime.now(timezone.utc).isoformat(),
                "summary": result.basic_stats,
                "config": result.config.to_dict(), "input": result.metadata,
                "segmentation": provenance or {"kind": "generated", "backend": result.config.backend},
                "centroid_coordinates": "one-based X/Y pixels, matching MATLAB"}
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
    if result.config.pnc_mode == "spots":
        write_csv(directory / "spots.csv", result.spots or [],
                  ["SpotID", "Area", "CentroidX", "CentroidY", "AnchorPixel", "NucleusID"])
    visualization(result).save(directory / "visualization.png")
