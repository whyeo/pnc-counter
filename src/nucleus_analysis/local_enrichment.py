"""Raw local fold enrichment on cached, fixed candidate geometry."""

import warnings

import numpy as np
from scipy import ndimage as ndi

from .adaptive_pnc import AdaptiveFeatures
from .enrichment_pnc import prepare_enrichment

ALGORITHM = "raw-3x3-median-local-ring-v1"
DEFAULT_THRESHOLD = 1.8


def prepare_local_enrichment(image, masks, identifiers=None, calibration=None, min_distance=3):
    """Measure raw3x3/ring ratios once; threshold changes never prepare candidates."""
    image = np.asarray(image)
    identifiers = list(range(1, len(masks) + 1)) if identifiers is None else list(identifiers)
    proposed = prepare_enrichment(image, masks, identifiers, calibration, min_distance)
    sigma = ((.9, .9) if calibration is None else
             tuple(float(np.clip(.1 / v, .5, 4)) for v in calibration[::-1]))
    ry, rx = [int(np.ceil(20 * s)) for s in sigma]
    dy, dx = np.mgrid[-ry:ry+1, -rx:rx+1]
    rho = np.hypot(dy / sigma[0], dx / sigma[1])
    ring = (rho >= 12) & (rho <= 20)
    dy, dx = dy[ring], dx[ring]
    sectors = np.floor((np.arctan2(dy/sigma[0], dx/sigma[1]) % (2*np.pi)) / (2*np.pi/8)).astype(int)
    py, px = np.mgrid[-1:2, -1:2]
    py, px = py.ravel(), px.ravel()
    owner = np.zeros(image.shape, np.uint32)
    for identifier, pixels in sorted(zip(identifiers, masks), key=lambda p: (len(p[1]), p[0])):
        free = owner.ravel()[pixels] == 0
        owner.ravel()[pixels[free]] = identifier
    candidates = [dict(row, ProposalScore=row["SignalScore"],
                       ProposalReviewFlags=row.get("ReviewFlags", ""), SignalScore=0.,
                       LocalEnrichment=None, EnrichmentEligible=False, ReviewFlags="")
                  for row in proposed.candidates]
    measurements = {}
    for identifier, pixels in zip(identifiers, masks):
        if not len(pixels):
            continue
        yy, xx = np.unravel_index(pixels, image.shape)
        y0, y1 = max(0, int(yy.min())-12), min(image.shape[0], int(yy.max())+13)
        x0, x1 = max(0, int(xx.min())-12), min(image.shape[1], int(xx.max())+13)
        raw = image[y0:y1, x0:x1]
        mask = np.zeros(raw.shape, bool)
        mask[yy-y0, xx-x0] = True
        interior = ndi.binary_erosion(mask, border_value=0)
        owned = owner[y0:y1, x0:x1]
        rows = [r for r in candidates if r["NucleusID"] == identifier
                and r.get("CandidateStatus") == "measured" and r["Area"] >= 3]
        for start in range(0, len(rows), 128):
            batch = rows[start:start+128]
            cy = np.array([r["SeedY"]-y0 for r in batch], int)
            cx = np.array([r["SeedX"]-x0 for r in batch], int)
            y, x = cy[:, None]+dy, cx[:, None]+dx
            bounds = (y >= 0) & (x >= 0) & (y < raw.shape[0]) & (x < raw.shape[1])
            yc, xc = np.clip(y, 0, raw.shape[0]-1), np.clip(x, 0, raw.shape[1]-1)
            valid = bounds & interior[yc, xc]
            reference = np.where(valid, raw[yc, xc], np.nan)
            count = valid.sum(axis=1)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                background = np.nanmedian(reference, axis=1)
                variation = 1.4826 * np.nanmedian(np.abs(reference-background[:, None]), axis=1)
            sector_count = np.stack([valid[:, sectors == s].sum(axis=1) for s in range(8)], axis=1)
            y3, x3 = cy[:, None]+py, cx[:, None]+px
            in_bounds = (y3 >= 0) & (x3 >= 0) & (y3 < raw.shape[0]) & (x3 < raw.shape[1])
            y3, x3 = np.clip(y3, 0, raw.shape[0]-1), np.clip(x3, 0, raw.shape[1]-1)
            central = (in_bounds & mask[y3, x3] & (owned[y3, x3] == identifier)).all(axis=1)
            centers = raw[y3, x3]
            raw_median, raw_peak = np.median(centers, axis=1), centers.max(axis=1)
            other = (valid & (owned[yc, xc] != 0) & (owned[yc, xc] != identifier)).sum(axis=1)
            for i, row in enumerate(batch):
                eligible = bool(central[i] and owned[cy[i], cx[i]] == identifier and count[i] >= 64
                                and np.isfinite(background[i]) and background[i] > 0)
                flags = []
                if not central[i]:
                    flags.append("3x3 window crosses nucleus/ownership boundary")
                if count[i] < 64 or not np.isfinite(background[i]) or background[i] <= 0:
                    flags.append("insufficient local reference")
                if sector_count[i].min() < 4:
                    flags.append("one-sided reference")
                if other[i]:
                    flags.append("reference overlaps another mask owner")
                if calibration is None:
                    flags.append("pixel-scale fallback")
                if row.get("RawSupportPixels", 3) < 3:
                    flags.append("limited raw spatial support")
                ratio = float(raw_median[i]/background[i]) if eligible else None
                row.update(LocalEnrichment=ratio, SignalScore=ratio if eligible else 0.,
                           Raw3x3Median=float(raw_median[i]), Raw3x3Peak=float(raw_peak[i]),
                           LocalReferenceMedian=float(background[i]) if np.isfinite(background[i]) else None,
                           LocalReferencePixels=int(count[i]),
                           ReferenceVariation=float(variation[i]) if np.isfinite(variation[i]) else None,
                           MinimumReferenceSectorPixels=int(sector_count[i].min()),
                           EnrichmentEligible=eligible, ReviewFlags="; ".join(flags))
        valid_rows = [r for r in rows if r["EnrichmentEligible"]]
        best = max(valid_rows, key=lambda r: (r["SignalScore"], -r["SpotID"])) if valid_rows else None
        measurements[int(identifier)] = {
            "max_score": best["SignalScore"] if best else 0.,
            "background": best["LocalReferenceMedian"] if best else None,
            "noise": best["ReferenceVariation"] if best else None,
            "flags": best["ReviewFlags"] if best else ("insufficient local reference" if rows else ""),
            "status": "measured" if best else "unsupported" if rows else "no_candidate"}
    scores = np.zeros(image.shape, np.float32)
    lookup = np.zeros(len(candidates)+1, np.float32)
    for row in candidates:
        lookup[row["SpotID"]] = row["SignalScore"]
    scores[:] = lookup[proposed.labels]
    scores.flags.writeable = False
    return AdaptiveFeatures(scores, measurements, proposed.labels, tuple(candidates))


def select_local_enrichment(features, threshold):
    if isinstance(threshold, bool) or not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("Local enrichment threshold must be positive and finite")
    lookup = np.zeros(len(features.candidates)+1, np.uint32)
    selected = []
    for candidate in features.candidates:
        if candidate["EnrichmentEligible"] and candidate["LocalEnrichment"] >= threshold:
            row = {**candidate, "SpotID": len(selected)+1}
            lookup[candidate["SpotID"]] = row["SpotID"]
            selected.append(row)
    labels = lookup[features.labels]
    return labels > 0, labels, selected
