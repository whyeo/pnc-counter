"""Calibration, border rules, and explicit PNC spot measurements."""

import math
from dataclasses import replace

import numpy as np
from scipy import ndimage as ndi
from skimage import feature, measure, segmentation


def pixel_size(config, metadata):
    if config.pixel_size_x_um is not None:
        return config.pixel_size_x_um, config.pixel_size_y_um
    values = metadata.get("pixel_size_um", {})
    x, y = values.get("x"), values.get("y")
    if all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (x, y)):
        return x, y
    return None


def segmentation_config(config, metadata):
    if config.min_nucleus_area_um2 is None:
        return config
    size = pixel_size(config, metadata)
    if size is None:
        raise ValueError("Physical area thresholds require calibrated pixel sizes or explicit X/Y sizes in micrometers")
    area = size[0] * size[1]
    minimum = max(1, math.ceil(config.min_nucleus_area_um2 / area - 1e-9))
    maximum = math.floor(config.max_nucleus_area_um2 / area + 1e-9)
    if maximum < minimum:
        raise ValueError("Physical area range contains no representable pixel area")
    return replace(config, min_nucleus_area=minimum, max_nucleus_area=maximum,
                   min_nucleus_area_um2=None, max_nucleus_area_um2=None)


def touches_border(pixels, shape, margin=0):
    yy, xx = np.unravel_index(pixels, shape)
    return bool(yy.min() <= margin or xx.min() <= margin or yy.max() >= shape[0] - 1 - margin
                or xx.max() >= shape[1] - 1 - margin)


def marker_image(image, config):
    """Background subtraction is opt-in and only applies to spot mode."""
    if config.pnc_mode != "spots" or not config.spot_background_sigma:
        return image
    values = image.astype(float)
    corrected = np.maximum(0, values - ndi.gaussian_filter(values, config.spot_background_sigma))
    if np.issubdtype(image.dtype, np.integer):
        return np.floor(corrected + 0.5).astype(image.dtype)
    return corrected


def detect_spots(positive_pixels, config):
    """Split touching threshold components with distance watershed; filter by area.

    A spot is assigned by its nearest-to-centroid foreground pixel, so a centroid
    outside a concave spot cannot accidentally attach it to another nucleus.
    """
    labels = np.zeros(positive_pixels.shape, dtype=np.uint32)
    if config.pnc_mode not in ("spots", "adaptive", "prominence") or not positive_pixels.any():
        return labels, []
    components, _ = ndi.label(positive_pixels, structure=np.ones((3, 3)))
    distance = ndi.distance_transform_edt(positive_pixels)
    peaks = feature.peak_local_max(distance, min_distance=config.spot_min_distance,
                                   labels=components, exclude_border=False)
    seeds = np.zeros(positive_pixels.shape, dtype=np.int32)
    if len(peaks):
        seeds[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
    # Ensure even very small components receive a marker before area filtering.
    for region in measure.regionprops(components):
        coords = region.coords
        if not seeds[coords[:, 0], coords[:, 1]].any():
            y, x = coords[np.argmax(distance[coords[:, 0], coords[:, 1]])]
            seeds[y, x] = seeds.max() + 1
    split = segmentation.watershed(-distance, seeds, mask=positive_pixels)
    rows = []
    for region in measure.regionprops(split):
        if not config.spot_min_area <= region.area <= config.spot_max_area:
            continue
        identifier = len(rows) + 1
        yy, xx = region.coords.T
        labels[yy, xx] = identifier
        cy, cx = region.centroid
        y, x = region.coords[np.argmin((yy - cy)**2 + (xx - cx)**2)]
        rows.append({"SpotID": identifier, "Area": int(region.area), "CentroidX": float(cx + 1),
                     "CentroidY": float(cy + 1), "AnchorPixel": int(y * labels.shape[1] + x),
                     "NucleusID": 0})
    return labels, rows


def assign_spots(rows, masks, spot_rows):
    """Each spot is counted once, preferring the smallest accepted nucleus."""
    counts = {row["MaskID"]: 0 for row in rows}
    for spot in spot_rows:
        spot["NucleusID"] = 0
    for row, pixels in sorted(zip(rows, masks), key=lambda pair: (pair[0]["Area"], pair[0]["MaskID"])):
        if row["BadMask"]:
            continue
        for spot in spot_rows:
            anchor = spot["AnchorPixel"]
            k = np.searchsorted(pixels, anchor)
            if spot["NucleusID"] == 0 and k < len(pixels) and pixels[k] == anchor:
                spot["NucleusID"] = row["MaskID"]
                counts[row["MaskID"]] += 1
    return counts
