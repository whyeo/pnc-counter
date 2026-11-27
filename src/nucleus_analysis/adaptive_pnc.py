"""Background/noise-relative PNC candidates; scores are not probabilities.

Geometry and image measurements are prepared once. Changing sensitivity only
thresholds the cached score image and filters connected candidate puncta.
"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from skimage import feature, measure, segmentation

ALGORITHM = "intranuclear-tophat-mad-v1"


def sensitivity_threshold(sensitivity):
    """Logarithmic range: 0 is strict (100 noise units), 100 is sensitive (2)."""
    return 2.0 * 50.0**(1.0 - float(sensitivity) / 100.0)


@dataclass(frozen=True)
class AdaptiveFeatures:
    score: np.ndarray
    measurements: dict
    labels: np.ndarray
    candidates: tuple


def prepare_adaptive(image, masks, identifiers=None, calibration=None, min_distance=3):
    image = np.asarray(image)
    if image.ndim != 2 or not np.isfinite(image).all() or np.any(image < 0):
        raise ValueError("Adaptive PNC requires a finite nonnegative 2D image")
    identifiers = list(range(1, len(masks)+1)) if identifiers is None else list(identifiers)
    if len(masks) != len(identifiers):
        raise ValueError("One identifier is required per nucleus")
    # Use physical dimensions when calibrated; otherwise explicit pixel defaults.
    if calibration is None:
        sigma, radius = (1., 1.), (12, 12)
    else:
        x, y = calibration
        sigma = tuple(float(np.clip(.10 / size, .5, 4)) for size in (y, x))
        radius = tuple(int(np.clip(round(1.5 / size), 3, 40)) for size in (y, x))
    scores = np.zeros(image.shape, dtype=np.float32)
    owned = np.zeros(image.shape, dtype=bool)
    measurements = {}
    span = float(np.ptp(image.astype(float)))
    floor = max(span * 1e-6, np.finfo(float).eps * max(float(image.max()), 1.))
    for identifier, pixels in sorted(zip(identifiers, masks), key=lambda pair: (len(pair[1]), pair[0])):
        if not len(pixels):
            continue
        yy, xx = np.unravel_index(pixels, image.shape)
        y0, y1, x0, x1 = yy.min(), yy.max()+1, xx.min(), xx.max()+1
        mask = np.zeros((y1-y0, x1-x0), dtype=bool)
        mask[yy-y0, xx-x0] = True
        interior = ndi.binary_erosion(mask, border_value=0)
        if not interior.any():
            measurements[identifier] = {"background": 0., "noise": 0., "max_score": 0.}
            continue
        values = image[y0:y1, x0:x1].astype(float)
        nuclear_median = float(np.median(values[interior]))
        # Mask-normalized smoothing avoids dark surroundings creating artificial
        # bright nuclear rims. Median fill gives opening a neutral outside value.
        weight = ndi.gaussian_filter(mask.astype(float), sigma, mode="constant")
        numerator = ndi.gaussian_filter(values * mask, sigma, mode="constant")
        smooth = np.divide(numerator, weight, out=np.full_like(values, nuclear_median), where=weight > 1e-9)
        smooth[~mask] = nuclear_median
        background = ndi.grey_opening(smooth, size=tuple(2*r+1 for r in radius), mode="nearest")
        residual = smooth - background
        raw_residual = values - background

        def normalize(response):
            samples = response[interior]
            center = float(np.median(samples))
            noise = max(1.4826 * float(np.median(np.abs(samples-center))), floor)
            return (response-center) / noise, noise

        smooth_score, _ = normalize(residual)
        raw_score, noise = normalize(raw_residual)
        # Raw support prevents smoothing one hot pixel into a multi-pixel spot.
        score = np.maximum(0, np.minimum(smooth_score, raw_score))
        score[~interior] = 0
        available = ~owned[y0:y1, x0:x1] & mask
        target = scores[y0:y1, x0:x1]
        target[available] = score[available]
        owned[y0:y1, x0:x1][mask] = True
        measurements[int(identifier)] = {"background": float(np.median(background[interior])),
                                         "noise": noise, "max_score": float(score[interior].max())}
    scores.flags.writeable = False
    foreground = scores >= 2
    markers = np.zeros(image.shape, dtype=np.int32)
    peaks = feature.peak_local_max(scores, min_distance=min_distance,
                                  threshold_abs=np.nextafter(2., -np.inf), exclude_border=False)
    if len(peaks):
        markers[tuple(peaks.T)] = np.arange(1, len(peaks)+1)
        split = segmentation.watershed(-scores, markers, mask=foreground)
    else:
        split = markers
    labels = np.zeros(image.shape, dtype=np.uint32)
    candidates = []
    for region in measure.regionprops(split):
        yy, xx = region.coords.T
        peak = float(scores[yy, xx].max())
        # Fixed half-height support keeps candidate geometry independent of the
        # slider, so increasing sensitivity cannot delete an existing candidate.
        support = (split[region.slice] == region.label) & (scores[region.slice] >= max(2., peak/2))
        components, _ = ndi.label(support, structure=np.ones((3, 3)))
        py, px = region.coords[np.argmax(scores[yy, xx])]
        anchor_label = components[py-region.bbox[0], px-region.bbox[1]]
        sy, sx = np.nonzero(components == anchor_label)
        sy, sx = sy+region.bbox[0], sx+region.bbox[1]
        identifier = len(candidates)+1
        labels[sy, sx] = identifier
        cy, cx = float(sy.mean()), float(sx.mean())
        k = np.argmin((sy-cy)**2+(sx-cx)**2)
        candidates.append({"SpotID": identifier, "Area": len(sy), "CentroidX": cx+1, "CentroidY": cy+1,
                           "AnchorPixel": int(sy[k]*image.shape[1]+sx[k]), "NucleusID": 0, "SignalScore": peak})
    labels.flags.writeable = False
    return AdaptiveFeatures(scores, measurements, labels, tuple(candidates))


def select_adaptive(features, sensitivity, min_area=3, max_area=500):
    cutoff = sensitivity_threshold(sensitivity)
    lookup = np.zeros(len(features.candidates)+1, dtype=np.uint32)
    rows = []
    for candidate in features.candidates:
        if candidate["SignalScore"] < cutoff or not min_area <= candidate["Area"] <= max_area:
            continue
        row = {**candidate, "SpotID": len(rows)+1}
        lookup[candidate["SpotID"]] = row["SpotID"]
        rows.append(row)
    labels = lookup[features.labels]
    return labels > 0, labels, rows


def adaptive_foreground(features, sensitivity, min_area=3, max_area=500):
    """Keep connected supra-threshold candidates; geometry is otherwise fixed."""
    return select_adaptive(features, sensitivity, min_area, max_area)[0]
