# Correcting and reviewing nuclei

Process images normally, select a completed result, and click **Review / correct
selected**. Double-clicking a result opens the same window. To continue a saved
review, use **Open saved analysis** and select that revision's `analysis.json`.
Review uses the saved projections and thresholds; SAM, its checkpoint, and the
original ND2/TIFF files are not required.

## Selection and drawing

Click a nucleus or select its ID in the sidebar. Ctrl+click selects several for
merge, reject, delete, or flag operations. Green boundaries show selection;
yellow boundaries show flags. Accepted nuclei are blue (PNC+) or pink (PNC-),
and rejected objects remain gray. Selected green boundaries take precedence over
yellow flags; the sidebar still shows the flag.

Switch between DAPI, PNC, DAPI + PNC, and the thresholded PNC image to inspect a
detection. The mouse wheel zooms around the pointer. Middle-button dragging or
the scrollbars pan. **Fit image** restores a whole-field view. Hiding overlays
allows inspection of the underlying image without labels.

For **Add**, choose the tool and draw an outline around a missed nucleus. For
**Redraw**, select exactly one existing nucleus first, choose the tool, and draw
its replacement boundary. Click polygon vertices or drag a freehand outline;
**Enter / Finish outline** closes and applies it. Right-click removes the last
outline point. **Esc / Cancel outline** abandons the unfinished outline.

Manual outlines must describe a connected object containing at least three
pixels. They bypass automatic nucleus-area limits, allowing corrections to small
or partial border nuclei. They cannot steal pixels from another detection:
overlapping additions/redraws are rejected with the conflicting nucleus ID.
Delete an incorrect duplicate, merge appropriate parts, or redraw tighter first.
Adding or redrawing a nucleus does not invoke the SVM again.

## Decisions and geometry changes

| Action | Geometry and counting behavior |
| --- | --- |
| Reject / exclude | Keeps the boundary and ID for inspection; removes it from the denominator and PNC+ count |
| Accept / restore | Restores a rejected nucleus to counting; its positive-pixel count determines PNC status |
| Flag for follow-up | Highlights the boundary yellow and marks the CSV; keeps it counted until a decision is made |
| Clear flag | Removes the follow-up marker |
| Delete selected | Removes geometry from the current review; undo can restore it |
| Redraw | Replaces the boundary while preserving its ID, flag, and acceptance decision |
| Split | Draw around **one part** of the selected nucleus; its intersection and the remaining pixels must form two connected parts, each at least three pixels |
| Merge | Unions the selected masks into one accepted object and retains their lowest ID; inspect disconnected fragments before using it |

Split conserves the original pixels exactly; it does not discard an artificial
cut line. One part retains the existing ID and the other receives a new ID.
Merge records the original source IDs, is marked as a manual geometry edit, and
preserves a follow-up flag if any input was flagged. Acceptance of a rejected
mask that would substantially overlap an accepted mask is blocked to prevent
double counting. Existing small automatic overlaps are retained in the original
snapshot rather than silently rewritten.

The positive-pixel cutoff and threshold image come from the saved analysis, and
the current cutoff is displayed at the top. Counts update immediately after each
edit. Geometry measurements are recomputed in a background thread when saving.
Manual acceptance/rejection decisions override automatic SVM and overlap
suppression; explicit corrections are not silently removed during export.

**Ctrl+Z** undoes and **Ctrl+Y** redoes edits in the current window. **Reset to
original** restores the original geometry and decisions and can itself be undone.
IDs of unaffected nuclei stay stable. Undo/redo stacks last for the current
session; original snapshots and the audit history persist across saves/reopening.

Version 0.4 adds review queues, reviewer notes, confirmation state, manual PNC
calls, verified reference sets, and optional spot counting. See the
[accuracy workflow guide](accuracy-workflow.md). Geometry changes reset
confirmation and manual PNC overrides. To verify an empty field, select no nuclei
and press **Confirm geometry + PNC**. Border-excluded detections remain excluded
regardless of manual acceptance.

## Saved revisions

**Save new revision** (Ctrl+S) asks for a parent folder and creates a unique
`review-TIMESTAMP-ID` directory inside it. Each revision is self-contained and
includes:

- Corrected `nuclei.csv`, `summary.csv`, `analysis.json`, `images.npz`, and
  `visualization.png`. Flagged outlines are yellow in the exported visualization.
- `nuclei_masks.npz`: exact reviewed candidate geometry. Stable IDs and decisions
  are stored in the CSV and review document rather than inferred from area order.
- `reviewed_labels.tif`: uint32 instance labels, zero background, one ID per
  accepted nucleus. Rejected objects are excluded; flagged accepted objects remain.
- `review.json`: decisions, flags, original source IDs, timestamped operations,
  file checksums, and the original configuration.
- `original_masks.npz`: the original geometry, allowing reset even when the raw
  image or original result directory is no longer available.

The original result directory, previously saved revisions, and original batch
summary are not overwritten. The desktop row switches to the newly saved counts
and visualization. The revision's own summary contains the corrected counts.
Resolve flags and inspect the review before treating exported labels as ground
truth: a flag marks uncertainty rather than a completed annotation.

NPZ files contain only numerical arrays and do not require pickle. Reopening
checks mask/projection checksums. New analysis exports preserve exact candidate
masks, including overlaps. Older v0.2 exports can recover these from their
recorded segmentation cache/import. If only label images survive, a visible
warning explains that overlapped portions of earlier masks may be missing.

CLI `--masks` imports geometry only and does not restore manual decisions or
flags. Reopen `analysis.json` through the app or `ReviewSession.open` to retain
the complete review state.

New review documents use schema version 2, including notes, confirmation,
reviewer identity, PNC overrides, and measurement-CSV checksums. Version 1 reviews
remain readable; detections start unverified because that format did not record
explicit verification.

## Headless review API

```python
from nucleus_analysis import ReviewSession

review = ReviewSession.open("results/sample-output")
review.mark([12], flagged=True)
review.mark([17], rejected=True)
review.redraw(4, [(120, 80), (145, 82), (148, 110), (118, 108)])
print(review.counts()[0])
directory, counts = review.save("results/reviews")
```

Outline points are zero-based `(x, y)` image coordinates. CSV centroids retain
the original one-based MATLAB convention. Saved accepted-label TIFFs can be
used with `tools/compare_segmentations.py` to compare a reviewed reference with
a model prediction.
