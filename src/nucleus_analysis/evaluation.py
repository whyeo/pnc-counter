"""One-to-one instance-mask agreement for reviewed labels or legacy baselines."""

import numpy as np
from scipy.optimize import linear_sum_assignment


def compare_labels(reference, predicted, iou_threshold=0.5):
    reference, predicted = np.asarray(reference), np.asarray(predicted)
    if reference.shape != predicted.shape or reference.ndim != 2:
        raise ValueError("Reference and prediction must be matching 2D label images")
    if not 0 < iou_threshold <= 1:
        raise ValueError("IoU threshold must be in (0, 1]")
    if any(not np.issubdtype(x.dtype, np.integer) or x.min() < 0
           for x in (reference, predicted)):
        raise ValueError("Labels must be nonnegative integers, with zero as background")
    ref_ids, ref = np.unique(reference, return_inverse=True)
    pred_ids, pred = np.unique(predicted, return_inverse=True)
    counts = np.bincount(ref.ravel() * len(pred_ids) + pred.ravel(),
                         minlength=len(ref_ids) * len(pred_ids)).reshape(len(ref_ids), len(pred_ids))
    unions = counts.sum(axis=1)[:, None] + counts.sum(axis=0)[None, :] - counts
    iou = np.divide(counts, unions, out=np.zeros_like(counts, dtype=float), where=unions > 0)
    ref_present, pred_present = ref_ids > 0, pred_ids > 0
    iou = iou[np.ix_(ref_present, pred_present)]
    # Maximize match count first, then IoU; plain maximum-IoU matching can yield
    # fewer above-threshold pairs on split/merge cases.
    benefit = (iou >= iou_threshold).astype(float) + iou / (min(iou.shape, default=0) + 1)
    rows, cols = linear_sum_assignment(benefit, maximize=True)
    good = iou[rows, cols] >= iou_threshold
    matched = int(good.sum())
    n_reference, n_predicted = iou.shape
    return {"iou_threshold": iou_threshold, "n_reference": n_reference,
            "n_predicted": n_predicted, "matched": matched,
            "unmatched_reference": n_reference - matched,
            "unmatched_prediction": n_predicted - matched,
            "precision": matched / n_predicted if n_predicted else None,
            "recall": matched / n_reference if n_reference else None,
            "f1": 2 * matched / (n_reference + n_predicted) if n_reference + n_predicted else None,
            "mean_matched_iou": float(iou[rows[good], cols[good]].mean()) if matched else None}
