"""Research-only enrichment prototype with auditable, permissive candidates.

No legacy/adaptive/prominence protocol is changed. Morphology and Z are recorded
as evidence, never turned into a hard biological veto. Thresholding reuses fixed
features; all seed losses remain in the candidate table. Scores are signal
measures, not biological probabilities.
"""

import numpy as np
from scipy import ndimage as ndi
from skimage import feature, measure, segmentation

from .adaptive_pnc import AdaptiveFeatures

ALGORITHM = "nuclear-local-enrichment-v1"
MAPPING = "0.1 * 20 ** (1 - sensitivity / 100)"
PARAMETERS = {"reference_percentiles": [20, 80], "smooth_um": .10, "background_um": 1.5,
              "smooth_fallback_px": .9, "background_fallback_px": 10.,
              "seed_noise_multiplier": 1., "seed_reference_fraction": .005,
              "growth_noise_multiplier": .25, "growth_reference_fraction": .001,
              "growth_peak_fraction": .15, "half_height_fraction": .5,
              "morphology": "supporting flags only", "z": "supporting measurements only",
              "score": "max(0, signed integrated local excess) / (nuclear reference * sqrt(area))"}


def sensitivity_threshold(sensitivity):
    if isinstance(sensitivity, bool) or not np.isfinite(sensitivity) or not 0 <= sensitivity <= 100:
        raise ValueError("Sensitivity must be finite and in [0, 100]")
    return .1 * 20. ** (1 - float(sensitivity) / 100)


def prepare_enrichment(image, masks, identifiers=None, calibration=None, min_distance=3,
                       *, support="growth", evidence=None, mixture=False):
    image = np.asarray(image)
    if image.ndim != 2 or not image.size or not np.isfinite(image).all() or np.any(image < 0):
        raise ValueError("Enrichment requires a finite nonnegative 2D image")
    if support not in ("growth", "half"):
        raise ValueError("Support must be growth or half")
    if calibration is not None and (len(calibration) != 2 or not np.isfinite(calibration).all()
                                    or min(calibration) <= 0):
        raise ValueError("Calibration must contain positive X/Y pixel sizes")
    identifiers = list(range(1, len(masks) + 1)) if identifiers is None else list(identifiers)
    if len(identifiers) != len(masks):
        raise ValueError("One identifier is required per nucleus")
    sigma = ((.9, .9) if calibration is None else
             tuple(float(np.clip(.1 / v, .5, 4)) for v in calibration[::-1]))
    broad = ((10., 10.) if calibration is None else
             tuple(float(np.clip(1.5 / v, 4, 40)) for v in calibration[::-1]))
    labels = np.zeros(image.shape, np.uint32)
    scores = np.zeros(image.shape, np.float32)
    owned = np.zeros(image.shape, bool)
    candidates, measurements = [], {}
    for identifier, pixels in sorted(zip(identifiers, masks), key=lambda pair: (len(pair[1]), pair[0])):
        if not len(pixels):
            continue
        yy, xx = np.unravel_index(pixels, image.shape)
        y0, y1, x0, x1 = yy.min(), yy.max()+1, xx.min(), xx.max()+1
        sl = np.s_[y0:y1, x0:x1]
        values = image[sl].astype(float)
        mask = np.zeros(values.shape, bool)
        mask[yy-y0, xx-x0] = True
        mask &= ~owned[sl]
        owned[sl] |= mask
        if not mask.any():
            continue
        interior = ndi.binary_erosion(mask, border_value=0)
        reference_region = interior if interior.sum() >= 8 else mask
        q20, q80 = np.percentile(values[reference_region], [20, 80])
        reference_mask = reference_region & (values >= q20) & (values <= q80)
        if not reference_mask.any():
            reference_mask = reference_region
        nuclear = float(np.median(values[reference_mask]))
        numerical = max(float(values[mask].max()) * 1e-6, 1e-12)
        normalizer = max(nuclear, numerical)

        def smooth(data, weights, scale, fallback):
            weight = ndi.gaussian_filter(weights.astype(float), scale, mode="constant")
            numerator = ndi.gaussian_filter(data * weights, scale, mode="constant")
            return np.divide(numerator, weight, out=np.full_like(data, fallback), where=weight > 1e-9)

        local = smooth(values, reference_mask, broad, nuclear)
        smoothed = smooth(values, mask, sigma, nuclear)
        residual = values - smoothed
        samples = residual[reference_region]
        noise = max(1.4826 * float(np.median(np.abs(samples - np.median(samples)))), numerical)
        response = np.where(mask, smoothed - local, 0.)
        seed_floor = max(noise, .005 * normalizer)
        growth_floor = max(.25 * noise, .001 * normalizer)
        peaks = feature.peak_local_max(response, min_distance=min_distance, threshold_abs=0,
                                       exclude_border=False, labels=mask.astype(np.uint8))
        if len(peaks):
            peaks = peaks[np.lexsort((peaks[:, 1], peaks[:, 0]))]
        eligible = response[tuple(peaks.T)] >= seed_floor if len(peaks) else np.empty(0, bool)
        seeds = peaks[eligible]
        markers = np.zeros(mask.shape, np.int32)
        if len(seeds):
            markers[tuple(seeds.T)] = np.arange(1, len(seeds)+1)
        split = segmentation.watershed(-response, markers, mask=mask & (response >= growth_floor))
        regions = {r.label: r for r in measure.regionprops(split)}
        mixture_info = None
        if mixture:
            from .intensity_mixture import fit_intensity_mixture

            mixture_info = fit_intensity_mixture(values[reference_region])
        nucleus_rows = []
        for py, px in peaks[~eligible]:
            candidates.append({"SpotID": len(candidates)+1, "NucleusID": int(identifier), "Area": 0,
                "CentroidX": float(px+x0+1), "CentroidY": float(py+y0+1),
                "AnchorPixel": int((py+y0)*image.shape[1]+px+x0), "SignalScore": 0.,
                "CandidateStatus": "discarded: below permissive seed floor", "SeedResponse": float(response[py, px]),
                "SeedFloor": seed_floor, "ReviewFlags": "not measured; seed below extraction floor"})
        for seed_id, (py, px) in enumerate(seeds, 1):
            region = regions.get(seed_id)
            if region is None:
                continue  # All eligible seeds are >= growth_floor, so this is defensive only.
            peak = float(response[py, px])
            fraction = .15 if support == "growth" else .5
            connected, _ = ndi.label((split[region.slice] == seed_id)
                                     & (response[region.slice] >= max(growth_floor, fraction * peak)),
                                     structure=np.ones((3, 3)))
            component = connected[py-region.bbox[0], px-region.bbox[1]]
            sy, sx = np.nonzero(connected == component)
            sy, sx = sy+region.bbox[0], sx+region.bbox[1]
            area = len(sy)
            raw_excess = values[sy, sx] - local[sy, sx]
            signed = float(raw_excess.sum())
            positive = float(np.maximum(raw_excess, 0).sum())
            ring_mask = np.zeros_like(mask)
            ring_mask[sy, sx] = True
            ring = ndi.binary_dilation(ring_mask, iterations=3) & reference_mask & (split == 0)
            ring_samples = values[ring]
            ring_bg = float(np.median(ring_samples)) if len(ring_samples) >= 8 else float(np.mean(local[sy, sx]))
            score = max(0., signed) / (normalizer * np.sqrt(area))
            raw_support = int(np.count_nonzero(raw_excess > noise))
            max_fraction = float(max(float(raw_excess.max()), 0.) / positive) if positive else 0.
            flags = []
            if calibration is None:
                flags.append("uncertain scale: pixel fallback")
            if np.any(~interior[sy, sx]):
                flags.append("boundary support")
            if raw_support < 3 or max_fraction > .8:
                flags.append("limited raw spatial support / possible hot pixel")
            if area > 500:
                flags.append("large/diffuse support")
            if np.issubdtype(image.dtype, np.integer) and np.any(values[sy, sx] == np.iinfo(image.dtype).max):
                flags.append("saturation")
            best_z, focus, z_score = None, None, None
            if evidence:
                planes = evidence["plane"][sy+y0, sx+x0]
                valid = planes >= 0
                if valid.any():
                    unique, counts = np.unique(planes[valid], return_counts=True)
                    best_z = int(unique[np.argmax(counts)])
                    same = planes == best_z
                    focus = float(same.sum() / area)
                    z_score = float(evidence["score"][sy+y0, sx+x0][same].mean())
                    if focus < .5:
                        flags.append("mixed source planes: supporting evidence only")
            else:
                flags.append("projection-only evidence")
            mix_fraction, mix_score = None, None
            if mixture_info is not None:
                threshold = mixture_info.get("threshold")
                mix_fraction = float(np.mean(values[sy, sx] >= threshold)) if threshold is not None else 0.
                mix_score = score * np.sqrt(mix_fraction)
            cy, cx = float(sy.mean()), float(sx.mean())
            anchor = np.argmin((sy-cy)**2+(sx-cx)**2)
            row = {"SpotID": len(candidates)+1, "NucleusID": int(identifier), "Area": area,
                   "Area_um2": float(area * calibration[0] * calibration[1]) if calibration else None,
                   "CentroidX": cx+x0+1, "CentroidY": cy+y0+1,
                   "AnchorPixel": int((sy[anchor]+y0)*image.shape[1]+sx[anchor]+x0),
                   "SeedY": int(py+y0), "SeedX": int(px+x0), "SeedResponse": peak,
                   "SeedFloor": seed_floor, "GrowthFloor": growth_floor,
                   "CandidateStatus": "measured", "SignalScore": float(score),
                   "NuclearReference": nuclear, "LocalRingReference": ring_bg, "ReferencePixels": int(reference_mask.sum()),
                   "LocalContrast": float((values[sy, sx].mean()-ring_bg)/max(ring_bg, numerical)),
                   "NuclearContrast": float((values[sy, sx].mean()-nuclear)/normalizer),
                   "SignedIntegratedExcess": signed, "PositiveIntegratedExcess": positive,
                   "IntegratedEnrichment": signed/normalizer, "Noise": noise, "RawSupportPixels": raw_support,
                   "LargestPixelFraction": max_fraction, "BestZ": best_z, "ZFocusFraction": focus,
                   "ZScore": z_score, "MixtureSupportFraction": mix_fraction, "MixtureScore": mix_score,
                   "ReviewFlags": "; ".join(flags)}
            labels[sy+y0, sx+x0] = row["SpotID"]
            scores[sy+y0, sx+x0] = score
            candidates.append(row)
            nucleus_rows.append(row)
        measurements[int(identifier)] = {"background": nuclear, "noise": noise,
            "reference_pixels": int(reference_mask.sum()), "candidate_count": len(nucleus_rows),
            "discarded_seeds": int((~eligible).sum()),
            "max_score": max((r["SignalScore"] for r in nucleus_rows), default=0.), "mixture": mixture_info}
    labels.flags.writeable = scores.flags.writeable = False
    return AdaptiveFeatures(scores, measurements, labels, tuple(candidates))


def select_enrichment(features, sensitivity, *, calibrated_floor=None, mixture=False):
    cutoff = sensitivity_threshold(sensitivity)
    if calibrated_floor is not None:
        if not np.isfinite(calibrated_floor) or calibrated_floor < 0:
            raise ValueError("Calibrated signal floor must be finite and nonnegative")
        cutoff = max(cutoff, calibrated_floor)
    lookup = np.zeros(len(features.candidates)+1, np.uint32)
    selected = []
    for row in features.candidates:
        value = row.get("MixtureScore") if mixture else row["SignalScore"]
        if row["CandidateStatus"] != "measured" or value is None or value < cutoff:
            continue
        selected.append({**row, "CandidateID": row["SpotID"], "SpotID": len(selected)+1})
        lookup[row["SpotID"]] = selected[-1]["SpotID"]
    labels = lookup[features.labels]
    return labels > 0, labels, selected
