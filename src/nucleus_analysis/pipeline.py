"""Measurements and PNC classification, independently usable from GUI or CLI."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from skimage import measure

from .adaptive_pnc import prepare_adaptive, select_adaptive, sensitivity_threshold
from .config import AnalysisConfig
from .imaging import Projections, read_image
from .morphology import legacy_circularity, legacy_solidity
from .phenotype import (
    assign_spots,
    detect_spots,
    marker_image,
    pixel_size,
    segmentation_config,
    touches_border,
)
from .pnc_evidence import selected_evidence
from .prominence_pnc import prepare_prominence, select_prominence
from .prominence_pnc import sensitivity_threshold as prominence_threshold
from .quality import is_bad_mask
from .segmentation import Segmenter, load_masks, validate_candidates


@dataclass
class AnalysisResult:
    basic_stats: dict
    full_stats: list[dict]
    images: dict[str, np.ndarray]
    config: AnalysisConfig
    metadata: dict
    masks: list[np.ndarray] | None = None
    spots: list[dict] | None = None
    candidates: tuple | None = None


def threshold_pnc(image, config):
    image = np.asarray(image)
    if config.threshold_mode == "global":
        median = float(np.median(image))
        threshold = median + (median - float(image.min())) * (3 + 0.01 * config.image_threshold)
        return image > threshold
    values = image.astype(np.float64)
    if np.issubdtype(image.dtype, np.integer):
        values /= np.iinfo(image.dtype).max
    elif values.min() < 0 or values.max() > 1:
        raise ValueError("Floating-point PNC images must be in [0, 1] for local thresholding")
    sensitivity = (100 - config.image_threshold) * 0.001
    # MATLAB adaptthresh(..., Statistic='gaussian') uses NeighborhoodSize as
    # Gaussian sigma, with imgaussfilt's default radius ceil(2*sigma).
    sigma = config.neighborhood_size
    local_mean = ndi.gaussian_filter(values, sigma=sigma, mode="nearest", truncate=2.0)
    threshold = np.clip((1.6 - sensitivity) * local_mean, 0, 1)
    return values > threshold


def _distribution(row, name, values):
    values = np.asarray(values, dtype=np.float64)
    # MATLAB's default prctile/iqr uses the Hazen quantile convention.
    row[f"{name}_IQR"] = float(np.diff(np.percentile(values, [25, 75], method="hazen"))[0])
    row[f"{name}_Mean"] = float(values.mean())
    row[f"{name}_Std"] = float(values.std(ddof=1)) if len(values) > 1 else 0.0


def _measure_mask(idx, shape, dapi_mean, dapi_max, percentiles):
    yy, xx = np.unravel_index(idx, shape)
    # Pad the local crop far enough to preserve the full-image Gaussian result.
    y0, y1 = max(0, yy.min() - 40), min(shape[0], yy.max() + 41)
    x0, x1 = max(0, xx.min() - 40), min(shape[1], xx.max() + 41)
    mask = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    mask[yy - y0, xx - x0] = True
    smoothed = ndi.gaussian_filter(mask.astype(float), sigma=20, mode="nearest", truncate=2) > 0.5
    props = measure.regionprops(mask.astype(np.uint8))[0]
    # MATLAB's pixel-area ellipse includes each pixel's intrinsic variance 1/12.
    eigenvalues = np.asarray(props.inertia_tensor_eigvals) + 1 / 12
    eccentricity = np.sqrt(max(0, 1 - eigenvalues[1] / eigenvalues[0]))
    row = {"Area": len(idx),
           "Smoothness": float(np.count_nonzero(mask & smoothed) / np.count_nonzero(mask | smoothed)),
           "CentroidX": float(xx.mean() + 1), "CentroidY": float(yy.mean() + 1),
           "Circularity": float(legacy_circularity(mask, len(idx))),
           "Eccentricity": float(eccentricity), "Solidity": legacy_solidity(mask)}
    for name, image in (("PercentileIntensity", percentiles), ("MeanIntensity", dapi_mean),
                        ("MaxIntensity", dapi_max)):
        _distribution(row, name, image.ravel()[idx])
    return row


def analyze(projections: Projections, config=None, masks=None, segmenter=None, *,
            mask_ids=None, rejected_ids=None, suppress_overlaps=True, positive_overrides=None):
    config = config or AnalysisConfig()
    mean, maximum, pnc = projections.dapi_mean, projections.dapi_max, projections.pnc_max
    if mean.ndim != 2 or mean.shape != maximum.shape or mean.shape != pnc.shape:
        raise ValueError("Projections must be matching two-dimensional images")
    if masks is None:
        effective = segmentation_config(config, projections.metadata)
        segmenter = segmenter or Segmenter(effective)
        segmenter.config = effective
        masks = segmenter.generate(maximum)
    segmentation_config(config, projections.metadata)  # Validate physical settings even for explicit masks.
    masks = validate_candidates(masks, maximum.shape)
    if mask_ids is not None:
        if (len(mask_ids) != len(masks) or len(set(mask_ids)) != len(mask_ids)
                or any(not isinstance(i, (int, np.integer)) or not 0 < i <= np.iinfo(np.uint32).max
                       for i in mask_ids)):
            raise ValueError("mask_ids must contain one unique positive uint32 ID per nonempty mask")
        entries = list(zip(mask_ids, masks))
    else:
        entries = [(None, idx) for idx in sorted(masks, key=len)]
    adaptive = config.pnc_mode in ("adaptive", "prominence")
    positive_pixels = (np.zeros(pnc.shape, dtype=bool) if adaptive
                       else threshold_pnc(marker_image(pnc, config), config))
    spot_labels, spots = detect_spots(positive_pixels, config)
    calibration = pixel_size(config, projections.metadata)
    # Percentile ranks stay finite on constant images and tied intensities.
    histogram = np.bincount(maximum.ravel(), minlength=256)
    ranks = 100 * np.cumsum(histogram) / maximum.size
    percentiles = ranks[maximum]
    labels = {name: np.zeros(maximum.shape, dtype=np.uint32)
              for name in ("mask_overall", "mask_positive", "mask_negative", "mask_bad")}
    rows = []
    retained_masks = []
    positive = negative = bad = 0
    for identifier, idx in entries:
        occupied = labels["mask_overall"].ravel()[idx] > 0
        if suppress_overlaps and np.count_nonzero(occupied) > config.overlap_threshold * len(idx):
            continue
        row = {"MaskID": int(identifier) if identifier is not None else len(rows) + 1}
        row.update(_measure_mask(idx, maximum.shape, mean, maximum, percentiles))
        n_pixels = int(positive_pixels.ravel()[idx].sum())
        rejected = (row["MaskID"] in rejected_ids if rejected_ids is not None
                    else config.quality_filter == "legacy-svm" and is_bad_mask(row))
        row["RejectedByQuality"] = int(rejected)
        border = touches_border(idx, maximum.shape, config.border_margin)
        excluded = config.border_policy == "exclude" and border
        rejected = rejected or excluded
        row.update(TouchesBorder=int(border), ExcludedByBorder=int(excluded),
                   Area_um2=float(len(idx) * calibration[0] * calibration[1]) if calibration else None)
        row.update(NumberCh2PixelsPositive=n_pixels, BadMask=int(rejected),
                   Positive=int(not rejected and n_pixels >= config.positive_threshold))
        row.update(AutomaticPositive=row["Positive"], ManualPNCOverride="auto")
        if rejected:
            labels["mask_bad"].ravel()[idx] = row["MaskID"]
            bad += 1
        else:
            labels["mask_overall"].ravel()[idx] = row["MaskID"]
            if row["Positive"]:
                labels["mask_positive"].ravel()[idx] = row["MaskID"]
                positive += 1
            else:
                labels["mask_negative"].ravel()[idx] = row["MaskID"]
                negative += 1
        rows.append(row)
        retained_masks.append(idx)
    prepared = None
    if adaptive:
        included = [(row, idx) for row, idx in zip(rows, retained_masks) if not row["BadMask"]]
        prepare = prepare_prominence if config.pnc_mode == "prominence" else prepare_adaptive
        select = select_prominence if config.pnc_mode == "prominence" else select_adaptive
        options = {"evidence": selected_evidence(projections, config), "z_policy": config.pnc_z_policy} if config.pnc_mode == "prominence" else {}
        prepared = prepare(pnc, [idx for _, idx in included],
                                    [row["MaskID"] for row, _ in included], calibration, config.spot_min_distance, **options)
        positive_pixels, spot_labels, spots = select(prepared, config.pnc_sensitivity,
                                                              config.spot_min_area, config.spot_max_area)
        for row, idx in zip(rows, retained_masks):
            values = prepared.measurements.get(row["MaskID"], {})
            row.update(NumberCh2PixelsPositive=int(positive_pixels.ravel()[idx].sum()),
                       PNCSignalScore=values.get("max_score"), PNCBackground=values.get("background"),
                       PNCNoise=values.get("noise"), PNCScoreThreshold=(prominence_threshold if config.pnc_mode == "prominence" else sensitivity_threshold)(config.pnc_sensitivity))
    if config.pnc_mode in ("spots", "adaptive", "prominence") or positive_overrides:
        spot_counts = assign_spots(rows, retained_masks, spots)
        labels["mask_positive"].fill(0)
        labels["mask_negative"].fill(0)
        positive = negative = 0
        for row, idx in zip(rows, retained_masks):
            row["NumberPNCSpots"] = spot_counts[row["MaskID"]]
            positive_call = (row["NumberPNCSpots"] >= config.min_spot_count if config.pnc_mode in ("spots", "adaptive", "prominence")
                             else row["NumberCh2PixelsPositive"] >= config.positive_threshold)
            row["AutomaticPositive"] = int(not row["BadMask"] and positive_call)
            row["ManualPNCOverride"] = "auto" if row["MaskID"] not in (positive_overrides or {}) else int(positive_overrides[row["MaskID"]])
            positive_call = (positive_overrides or {}).get(row["MaskID"], positive_call)
            row["Positive"] = int(not row["BadMask"] and positive_call)
            if not row["BadMask"]:
                labels["mask_positive" if row["Positive"] else "mask_negative"].ravel()[idx] = row["MaskID"]
                positive += row["Positive"]
                negative += not row["Positive"]
    total = positive + negative
    summary = {"percentage": 100 * positive / total if total else None,
               "n_negative": negative, "n_positive": positive, "n_bad": bad,
               "n_total": total, "n_masks": len(rows)}
    images = {"ch1": mean, "ch1_max": maximum, "ch2": pnc,
              "ch2_thresh": positive_pixels, **labels}
    if config.pnc_mode in ("spots", "adaptive", "prominence"):
        images["pnc_spots"] = spot_labels
    if prepared is not None:
        images["pnc_score"] = prepared.score
    if projections.pnc_evidence:
        images.update({"pnc_z_" + k: v for k, v in projections.pnc_evidence.items()})
    return AnalysisResult(summary, rows, images, config, projections.metadata, retained_masks, spots, prepared.candidates if prepared is not None else None)


def count_pnc(path, positive_threshold=None, *, config=None, masks=None, axes=None):
    """Analyze a single file; explicit masks permit replay of MATLAB segmentations."""
    from dataclasses import replace

    config = config or AnalysisConfig()
    if positive_threshold is not None:
        config = replace(config, positive_threshold=positive_threshold)
    projections = read_image(path, config, axes=axes)
    if isinstance(masks, (str, Path)):
        masks = load_masks(masks, projections.dapi_max.shape)
    return analyze(projections, config, masks=masks)
