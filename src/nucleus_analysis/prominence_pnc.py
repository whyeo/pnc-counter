"""Experimental training-free punctum scores with fixed, explainable candidates.

This is an additional protocol: legacy/adaptive-v1 analyses retain their methods.
Scores combine local/nuclear contrast, robust noise, spatial support, candidate
multiplicity, and optional same-plane evidence. They are not probabilities.
"""

import numpy as np
from scipy import ndimage as ndi
from skimage import feature, measure, segmentation

from .adaptive_pnc import AdaptiveFeatures, select_adaptive
from .pnc_evidence import scales

ALGORITHM = "multiscale-prominence-v1"
MAPPING = "2 * 20 ** (1 - sensitivity / 100)"


def sensitivity_threshold(sensitivity):
    return 2. * 20. ** (1 - float(sensitivity) / 100)


def prepare_prominence(image, masks, identifiers=None, calibration=None, min_distance=3,
                       *, evidence=None, z_policy="auto", variant="dog"):
    image = np.asarray(image)
    if image.ndim != 2 or not np.isfinite(image).all() or np.any(image < 0):
        raise ValueError("PNC prominence requires a finite nonnegative 2D image")
    if variant not in ("dog", "tophat") or z_policy not in ("auto", "projection"):
        raise ValueError("Unknown prominence variant or Z policy")
    identifiers = list(range(1, len(masks) + 1)) if identifiers is None else list(identifiers)
    if len(identifiers) != len(masks):
        raise ValueError("One identifier is required per nucleus")
    small, broad = scales(calibration)
    labels = np.zeros(image.shape, np.uint32)
    score_image = np.zeros(image.shape, np.float32)
    owned = np.zeros(image.shape, bool)
    candidates, measurements = [], {}
    use_z = bool(evidence) and z_policy == "auto"
    for identifier, pixels in sorted(zip(identifiers, masks), key=lambda p: (len(p[1]), p[0])):
        if not len(pixels):
            continue
        yy, xx = np.unravel_index(pixels, image.shape)
        y0, x0, y1, x1 = yy.min(), xx.min(), yy.max() + 1, xx.max() + 1
        region_slice = np.s_[y0:y1, x0:x1]
        mask = np.zeros((y1-y0, x1-x0), bool)
        mask[yy-y0, xx-x0] = True
        mask &= ~owned[region_slice]
        owned[region_slice] |= mask
        interior = ndi.binary_erosion(mask, border_value=0)
        if not interior.any():
            measurements[int(identifier)] = {"background": 0., "noise": 0., "max_score": 0.}
            continue
        values = image[region_slice].astype(float)
        nuclear = float(np.median(values[interior]))

        def smooth(sigma):
            weight = ndi.gaussian_filter(mask.astype(float), sigma, mode="constant")
            numerator = ndi.gaussian_filter(values * mask, sigma, mode="constant")
            return np.divide(numerator, weight, out=np.full_like(values, nuclear), where=weight > 1e-9)

        local_background = smooth(broad)
        if variant == "tophat":
            filled = np.where(mask, smooth(small[0]), nuclear)
            local_background = ndi.grey_opening(filled, size=tuple(2 * int(s) + 1 for s in broad))
        responses = np.stack([smooth(s) - local_background for s in small])
        response = responses.max(axis=0)
        highpass = values - smooth(small[0])
        samples = highpass[interior & (response <= np.percentile(response[interior], 80))]
        noise = 1.4826 * float(np.median(np.abs(samples - np.median(samples))))
        floor = max(noise, .02 * nuclear, float(values[mask].max()) * 1e-6, 1e-12)
        normalized = np.maximum(0, response / floor)
        normalized[~mask] = 0
        peaks = feature.peak_local_max(normalized, min_distance=min_distance,
                                       threshold_abs=1.5, exclude_border=False)
        markers = np.zeros(mask.shape, np.int32)
        if len(peaks):
            markers[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
        split = segmentation.watershed(-response, markers, mask=mask & (normalized >= 1.5))
        nucleus_candidates = []
        for region in measure.regionprops(split):
            ry, rx = region.coords.T
            py, px = region.coords[np.argmax(response[ry, rx])]
            peak = float(response[py, px])
            support = (split[region.slice] == region.label) & (response[region.slice] >= peak / 2)
            # Require raw spatial support as well as smoothed signal.
            support &= values[region.slice] - local_background[region.slice] >= peak / 2
            connected, _ = ndi.label(support, structure=np.ones((3, 3)))
            anchor = connected[py-region.bbox[0], px-region.bbox[1]]
            if not anchor:
                continue
            sy, sx = np.nonzero(connected == anchor)
            sy, sx = sy + region.bbox[0], sx + region.bbox[1]
            support_mask = np.zeros_like(mask)
            support_mask[sy, sx] = True
            # Local annulus and nuclear reference exclude all extracted signal.
            ring = ndi.binary_dilation(support_mask, iterations=max(2, min(12, int(max(broad) / 2))))
            ring &= interior & (split == 0)
            reference = values[ring] if ring.sum() >= 8 else values[interior & (split == 0)]
            bg = max(nuclear, float(np.median(reference))) if len(reference) else nuclear
            local_noise = (1.4826 * float(np.median(np.abs(reference - np.median(reference))))
                           if len(reference) else noise)
            prominence = max(0., float(np.mean(values[sy, sx])) - bg)
            denominator = max(noise, local_noise, .02 * abs(bg), float(values[mask].max()) * 1e-6, 1e-12)
            signal = min(peak / floor, prominence / denominator)
            flags = []
            boundary = bool(np.any(~interior[sy, sx]))
            if boundary:
                flags.append("boundary artifact")
            if calibration is None:
                flags.append("uncertain scale: pixel fallback")
            if np.issubdtype(image.dtype, np.integer) and np.any(values[sy, sx] == np.iinfo(image.dtype).max):
                flags.append("saturation")
            area = len(sy)
            # Tiny structures remain eligible (>=3 raw pixels), hot pixels do not.
            if area < 3:
                flags.append("isolated pixel / insufficient spatial support")
                signal = 0.
            extent = area / ((sy.max() - sy.min() + 1) * (sx.max() - sx.min() + 1))
            if boundary:
                signal = 0.
            if area > 500 or extent < .15:
                flags.append("diffuse or sparse structure")
                signal = 0.
            z_score, focus, best_z = None, None, None
            if use_z:
                zs = evidence["score"][sy+y0, sx+x0]
                planes = evidence["plane"][sy+y0, sx+x0]
                valid = planes >= 0
                if valid.any():
                    unique, counts = np.unique(planes[valid], return_counts=True)
                    best_z = int(unique[np.argmax(counts)])
                    same = planes == best_z
                    focus = float(same.sum() / area)
                    z_score = float(np.mean(zs[same]))
                    # A single focused plane can supply all required evidence.
                    signal = min(signal, z_score) * np.sqrt(focus)
                    if same.sum() < 3:
                        flags.append("insufficient same-plane spatial support")
                        signal = 0.
                    if focus < .5:
                        flags.append("incoherent projected peaks")
                else:
                    signal = 0.
            elif z_policy == "auto":
                flags.append("2D fallback: no saved per-plane evidence")
            cy, cx = float(sy.mean()), float(sx.mean())
            k = np.argmin((sy-cy)**2 + (sx-cx)**2)
            row = {"SpotID": len(candidates) + len(nucleus_candidates) + 1,
                   "Area": area, "Area_um2": float(area * calibration[0] * calibration[1]) if calibration else None,
                   "CentroidX": cx+x0+1, "CentroidY": cy+y0+1,
                   "AnchorPixel": int((sy[k]+y0)*image.shape[1]+sx[k]+x0), "NucleusID": int(identifier),
                   "SignalScore": float(signal), "LocalBackground": bg, "Noise": denominator,
                   "Prominence": prominence, "Extent": float(extent),
                   "ScaleIndex": int(np.argmax(responses[:, py, px])),
                   "BestZ": best_z, "ZScore": z_score, "ZFocusFraction": focus,
                   "ReviewFlags": "; ".join(flags)}
            nucleus_candidates.append((row, sy+y0, sx+x0))
        # A fixed peak multiplicity penalty limits chance detections in busy nuclei.
        penalty = np.sqrt(1 + np.log1p(len(nucleus_candidates)))
        for row, sy, sx in nucleus_candidates:
            row["CandidateCount"] = len(nucleus_candidates)
            row["MultiplicityPenalty"] = float(penalty)
            row["SignalScore"] /= penalty
            labels[sy, sx] = row["SpotID"]
            score_image[sy, sx] = row["SignalScore"]
            candidates.append(row)
        measurements[int(identifier)] = {"background": nuclear, "noise": floor,
                                         "max_score": max((r[0]["SignalScore"] for r in nucleus_candidates), default=0.)}
    score_image.flags.writeable = labels.flags.writeable = False
    return AdaptiveFeatures(score_image, measurements, labels, tuple(candidates))


def select_prominence(features, sensitivity, min_area=3, max_area=500):
    # Reuse the stable candidate selection implementation with our own mapping.
    equivalent = 100 * (1 - np.log(sensitivity_threshold(sensitivity) / 2) / np.log(50))
    return select_adaptive(features, equivalent, min_area, max_area)
