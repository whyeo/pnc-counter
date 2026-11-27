# Accuracy, calibration, review queues, and PNC spots

Version 0.4 adds four workflows. The default remains the original pixel-based
PNC rule with border nuclei included. These features provide tools for a real
accuracy study; the repository's MATLAB/SAM outputs are not human ground truth.

## 1. Build a verified reference set

Open an analysis in the correction window. Inspect DAPI and PNC signals, correct
boundaries, reject false detections, and add missed nuclei. Use **Reviewer / note
/ PNC call** to record your name, reasons, and an optional manual positive or
negative call. The automatic call remains available.

Use **Confirm geometry + PNC** on checked nuclei. Multi-selection can confirm
several after inspection. Resolve flags first. Geometry edits and manual PNC-call
changes invalidate confirmation. Changing recorded analysis settings also
requires renewed verification. For a truly empty field, select no nuclei and
explicitly confirm the empty field with the same button.

Click **Add verified reference**, choose a reference-set folder, assign a
**validation** or **test** split, and enter a specimen/acquisition group. Fields
from one specimen/group must stay in one split. Tune on validation fields and
evaluate the test set after choosing settings. Group names must reflect the
experiment's real independence; the app cannot infer specimen relationships.

Export requires a reviewer name, every detection confirmed, and no unresolved
flags. It creates a self-contained review revision and registers it in
`manifest.json`. Image hashes prevent duplicate registrations. Create a new
reference-set version when revising an already registered image's annotation.

Generate predictions normally using the same border protocol, then run:

```powershell
nucleus-benchmark references/manifest.json results/model-run --split test --output benchmark.json
# Equivalent from a checkout:
python tools/benchmark.py references/manifest.json results/model-run --split test --output benchmark.json
```

The evaluator matches images by saved projection content without raw files. It
excludes manually reviewed outputs from prediction discovery and requires one
prediction per image. It checks reference integrity and rejects split-group
leakage, missing/ambiguous predictions, and mismatched border rules.

Reports include one-to-one instance precision/recall/F1, weighted matched IoU
(`--iou`, default 0.5), nucleus-count MAE, PNC-positive-count MAE, and percentage
MAE in **percentage points**. Per-image signed errors, matched IDs, settings, and
source hashes are retained. End-to-end PNC metrics penalize unmatched positive
predictions as false positives and unmatched positive references as false
negatives. Wrong matched PNC calls are penalized even when aggregate counts agree.

Undefined metrics are JSON `null`. Two empty fields contribute zero count error
but no invented percentage or perfect F1. Biological accuracy requires human
references; synthetic test reports only validate the software.

Headless registration is supported:

```python
from nucleus_analysis import ReviewSession
from nucleus_analysis.benchmark import add_reference

review = ReviewSession.open("results/review-revision")
# Explicit review/confirmation must already be complete; no automatic labelling.
add_reference(review, "references", split="test", group="specimen-01")
```

## 2. Border rules and physical nucleus area

Open **Advanced settings → Nuclei / PNC / Acquisition** in the main app. Border policy is `include`
(legacy default) or `exclude`. A nucleus touches the border if any pixel is
within the configured inclusive pixel margin of an edge; zero means the outermost
row/column. Excluded nuclei keep IDs, geometry, and measurements but are omitted
from the denominator and positive count. `TouchesBorder`, `ExcludedByBorder`, and
the quality/manual rejection decision are recorded separately. Manual acceptance
does not override the border protocol.

Set both minimum and maximum nucleus area in **µm²** to override pixel-area bounds
for automatic segmentation. Pixel size comes from calibrated ND2 or OME-TIFF
metadata. Explicit X/Y micrometer sizes override metadata, including non-square
pixels. Plain TIFFs without calibration need explicit sizes. Missing calibration
produces an error instead of a guessed scale. `Area_um2` is exported when known.

```powershell
python -m nucleus_analysis data --checkpoint models/sam2.1_hiera_tiny.pt --border-policy exclude --min-nucleus-area-um2 50 --max-nucleus-area-um2 600
# If metadata has no calibration, also provide both:
# --pixel-size-x-um 0.1 --pixel-size-y-um 0.1
```

Those numerical areas are examples, not validated settings for every cell line.
Manual polygons bypass automatic area limits; the queue identifies out-of-range
objects. Border rules still apply to manual geometry. Border and PNC-mode changes
can reuse segmentation caches; physical-area changes invalidate caches through
the effective pixel bounds.

## 3. Prioritized review queue

The sidebar filters **all**, **unreviewed**, **uncertain**, **flagged**, or
**rejected** detections. **Next in review queue** selects and centers the next
object. Flags take priority, followed by border objects, PNC measurements near
the cutoff, unusual area/shape, and exclusions. Confirmed objects leave the
unreviewed/uncertain queues. Reasons are shown beside the selected nucleus.

These are heuristics, not calibrated confidence probabilities. Current caches
do not retain SAM confidence scores. The pixel cutoff margin defaults to three
pixels and is configurable; spot mode prioritizes measurements exactly at the
spot-count cutoff. Notes, reviewer identity, manual PNC overrides, and confirmation
persist in the CSV and checksummed review document.

## 4. Separate candidate PNC spot mode

Choose `pnc_mode=spots` in the options dialog or CLI. Pixel mode remains the
default; its `positive_threshold` is not reinterpreted as spot count. Spot mode
uses its own `min_spot_count`.

```powershell
python -m nucleus_analysis data --checkpoint models/sam2.1_hiera_tiny.pt --pnc-mode spots --min-spot-count 1 --spot-min-area 3 --spot-max-area 500 --spot-min-distance 3
```

The detector thresholds the PNC projection, splits touching foreground components
using distance watershed, and filters candidates by pixel area. Optional Gaussian
background subtraction (`spot_background_sigma`, default zero/off) happens before
thresholding and only affects spot mode. Spot area and spacing currently use pixels.

Each spot is assigned once using a foreground point nearest its centroid. That
point must lie inside an accepted nucleus. The smallest accepted nucleus wins
overlaps deterministically. Outside spots remain exported with `NucleusID=0` and
do not count toward positivity. Manual PNC overrides remain explicit decisions.

Outputs retain positive-pixel measurements and add `NumberPNCSpots`, `spots.csv`,
and `pnc_spots` labels in NPZ. The canvas and exported PNG show spot centers. The
CSV records area, one-based centroid, assignment anchor, and nucleus ID.

This is a **candidate puncta detector**, not a biologically validated PNC
detector. Noise, diffuse signal, nearby structures, merged puncta, and projection
can affect counts. Verify candidates on representative fields and benchmark on
held-out data before adopting a new positivity rule. Synthetic tests cover
isolated/touching spots, size/noise filtering, unique assignment, background
opt-in, manual calls, and saved-review consistency.
