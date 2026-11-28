# v0.7.0.dev2 local preview

This is a local experimental preview. Stable downloads remain v0.6.0. The owner
has not approved v0.7.0 finalization, tagging or publication.

## Try it locally

1. Run `dist/preview/PNC-Counter-0.7.0.dev2-Preview-Setup-x64.exe`. It installs
   **PNC Counter Preview**, with a separate identity and preferences from stable.
2. Choose **Set up later**, then **Open saved analysis**. Existing saved nuclei
   work without SAM or the raw image. No training or extra model is required.
3. Select **Multiscale prominence (preview)** in the review window. Move the
   sensitivity slider; inspect **PNC** with and without **Show masks**. Navigation
   and display contrast are shared. Green outlines indicate accepted candidates.
4. **Marker display range** takes raw minimum/maximum values. Reuse those values
   across images for a contrast-matched comparison; blank restores auto contrast.
   These display settings never change intensities used for calls.
5. A projection-only analysis says **2D projection scoring; no Z evidence used**.
   If its original raw source is available, **Load Z evidence from source** checks
   that all projections match, then prepares compact evidence using fixed nuclei.
   It switches to the experimental prominence method. Changed raw data are refused.
6. Select a nucleus, then **Inspect candidate Z plane** to view the source plane
   of its strongest candidate. The image is labeled inspection-only. **Return to
   maximum projection** restores the scoring representation. Plane inspection does
   not change calls. Missing raw files leave saved compact measurements usable.
7. **Save new revision** preserves the original counts, masks and manual overrides.
   **Use for next analysis** transfers the PNC protocol to later analyses. New raw
   image segmentation still needs the existing SAM setup.

The main input preview now uses the analysis maximum projection, rather than the
first plane. It labels zero-based channels, time and position. Its shared marker
display-range control applies across the selected source-image previews; completed
four-panel exports have their own recorded rendering.

Technical size, background and Z-policy settings remain under Advanced settings.
`pnc_z_policy=auto` uses compatible saved per-plane evidence; `projection` explicitly
uses 2D. Changing calibrated pixel sizes requires reloading Z evidence or selecting
projection mode. Pixel fallbacks are recorded when physical scale is unknown.
One focused Z-plane may support a punctum: there is no multi-slice continuity gate.

## What the comparison found

The same retained SAM geometry and the owner's existing whole-field 30/70 split
were used: 11 tuning fields, 26 validation fields. The shortlist was DoG prominence,
top-hat prominence and DoG with per-plane evidence, alongside adaptive-v1 and legacy.
Four sensitivities (25, 50, 75, 100) were declared before tuning.

No tested point met the stated proxy screen for negative reduction together with
positive/small preservation. The frozen diagnostic point was DoG 2D, sensitivity 25;
it was **rejected as a replacement**. Validation field means were:

| Group | Fields | Legacy | Frozen experimental point | Experimental positive/total nuclei |
| --- | ---: | ---: | ---: | ---: |
| Negative | 7 | 24.64% | 0.00% | 0/213 |
| Positive | 12 | 84.71% | 2.15% | 13/576 |
| Small PNC | 7 | 8.16% | 1.14% | 2/192 |

These are field-averaged call rates, not accuracy, sensitivity or specificity.
Folder membership is not per-cell truth. The validation fields had been examined
previously, so this follow-up remains exploratory. No validation result was used
to select another operating point. Sensitivity 50 in the interface is an
experimental starting value, not a validated biological cutoff.

The bounded noise rule reduces numerical instability but cannot establish PNC
identity. Tuning Z evidence reduced some incidental calls and also removed signal
in positive/small fields. Nucleolar identity is not inferred from dark DAPI regions.
No automatic method in this preview has demonstrated the required biological
trade-off. The legacy default remains unchanged.

The private local report is under
`validation/local/pnc-discrimination/v070-dev2/comparison-1/`; it contains the
declared plan, frozen configuration, full per-field denominators, distributions,
candidate measurements, source hashes and visual failures/ambiguous examples.
These inputs and outputs are ignored and must not be uploaded.

## Checks and practical limits

The implementation milestone passed 152 tests, including legacy compatibility,
monotonic slider acceptance, manual-call provenance, stale-response rejection,
cache/scale invalidation, Z fallback, source-plane inspection and revision parity.
All PNC measurements use CPU; slider updates and saved-mask remeasurement do not
invoke SAM. Installed-runtime timing and installer checks are recorded in the
local delivery report.

On the local Ryzen 7 5700X, 1040 x 1392 fields took approximately 1–3 seconds for
2D preparation. Cold raw-stack reading plus Z preparation took approximately
5–9 seconds, exceeding the few-second goal for that path. Cached slider timings
must be assessed separately, including debounce and rendering.

An optional spot-check of negative, clear and small examples should focus on
obvious misses, incidental bright structures and the intended PNC definition.
It is not a training session, and no classifier is fitted to review feedback.

## Reproduce the exploratory comparison

The original measurement implementation is commit `5a9d4fd`; the local plan records
every source-file SHA-256 and the split/export hashes. Later preview changes affect
versioning, background preparation and display labels, not the frozen detector.

```powershell
python tools/training_free_experiment.py plan --split validation/local/pnc-discrimination/heldout-30-70/split.json --output validation/local/new-comparison
python tools/training_free_experiment.py tune --output validation/local/new-comparison
python tools/training_free_experiment.py validate --output validation/local/new-comparison
```

Use a new directory for each declared experiment. Completed results are not
overwritten, and validation does not refit the threshold. The legacy/adaptive
comparators include the documented sensitivity-50 default as a diagnostic view;
additional displayed rates must not be used to reselect the frozen point.
