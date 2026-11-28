# PNC Counter Training Free Detection PRD

**Status:** Draft for the next v0.7.0 local preview.  
**Owner and release approver:** Repository owner.  
**Intended implementer:** The next coding agent working in this repository.  
**Date:** 2026-11-28.

## Purpose

Improve separation of genuine PNC signal from negative-control signal without
requiring model pretraining, a labeling campaign, or additional setup by the
biologist. Provide an explainable detector with useful defaults and one live
sensitivity slider. Preserve small PNCs while reducing incidental bright-spot
calls, and make the image shown to the user consistent with the measurement.

The owner finds the distinction clear by visual inspection. The next iteration
should use more of that image information through classical image processing
and Z-stack evidence. A supervised classifier is outside the required scope.

v0.7.0 may be finalized only after the owner tests it locally and explicitly
approves it. Continue with development versions and local preview installers;
do not create a v0.7.0 tag, publish a release, or replace the published v0.6.0.

## Product constraints

| Constraint | Requirement |
| --- | --- |
| Training | No required pretraining, fine-tuning, classifier fitting, or manual training set. |
| User effort | No mandatory labeling or control-calibration session before ordinary analysis. A short visual spot-check is validation, not training. |
| Runtime | Python only, local processing, offline analysis after dependency/model setup. |
| Dependencies | Prefer existing NumPy, SciPy, scikit-image, ND2, and Tk/Pillow dependencies. PNC scoring must run on CPU without a new neural model. |
| Nucleus segmentation | Reuse the existing SAM nucleus masks. Changing the nucleus model is not the main task. |
| Interface | Keep technical parameters in Advanced settings. Retain one understandable sensitivity slider. |
| Compatibility | Preserve legacy protocols, manual calls, reviewed geometry, original exports, and immutable revisions. |
| Distribution | Windows preview installer remains separate from the stable app and its preferences. macOS packaging is outside scope. |

## Current implementation

Start from the repository's existing implementation. The code baseline for this
PRD is commit `1d43fd346ddc0382e56a8768e11e76765ee0c5dd`, version `0.7.0.dev1`.
The published stable release is v0.6.0 at commit
`d56e429a448ea8b95a70140260573391c36d7c12`. Later documentation commits do not
change those code baselines.

The preview already contains:

- An optional background-aware PNC candidate detector. It estimates intranuclear
  background and robust noise, extracts connected candidates, and scores them.
- A debounced sensitivity slider, cached image measurements, fixed candidate
  geometry, stale-response protection, manual-call preservation, and protocol reuse.
- Saved revisions containing the method, sensitivity, candidate scores, and spot
  geometry. Slider updates do not rerun SAM.
- Separate preview installation identity, preferences, and output assets.
  Stable-release validation rejects development versions.
- 134 passing tests at the baseline commit, plus an installed-preview ND2 export
  check and an installed slider/save/reopen check. These establish functionality,
  not biological accuracy. Cached slider updates on tested HeLa examples took
  approximately 0.3–0.6 seconds including debounce and rendering.

The legacy method remains the default because the experimental method has not
demonstrated adequate negative-control separation. Do not present the existing
adaptive implementation as an already validated solution.

### Code map

| Area | Existing implementation |
| --- | --- |
| Initial channel preview | [workflow.py](../src/nucleus_analysis/workflow.py), especially `raw_preview` |
| Image reading and projections | [imaging.py](../src/nucleus_analysis/imaging.py) |
| Projection cache | [projection_cache.py](../src/nucleus_analysis/projection_cache.py) |
| Experimental adaptive PNC scores | [adaptive_pnc.py](../src/nucleus_analysis/adaptive_pnc.py) |
| Measurement and classification | [pipeline.py](../src/nucleus_analysis/pipeline.py) |
| Spot assignment and physical calibration | [phenotype.py](../src/nucleus_analysis/phenotype.py) |
| Review model and cached recounting | [review.py](../src/nucleus_analysis/review.py) |
| Review window and live slider | [editor.py](../src/nucleus_analysis/editor.py) |
| Main app and settings | [gui.py](../src/nucleus_analysis/gui.py), [config.py](../src/nucleus_analysis/config.py) |
| Exports | [output.py](../src/nucleus_analysis/output.py) |
| Control experiment | [pnc_control_experiment.py](../tools/pnc_control_experiment.py) |
| Installed slider test | [smoke_pnc_slider.py](../tools/smoke_pnc_slider.py) |
| Preview packaging | [build_windows.py](../tools/build_windows.py), [release_metadata.py](../tools/release_metadata.py) |
| Existing detector and GUI tests | [test_adaptive_pnc.py](../tests/test_adaptive_pnc.py) |

## Evidence and limitations

### Preview and analysis currently use different image representations

The initial ND2 preview reads one Z-plane. Analysis uses a maximum-intensity
projection across the selected stack. Saved-result views show the projection.

For the local HeLa negative-control `IMG2.nd2`, the same legacy PNC rule and
fixed nucleus masks produced 0 positive calls among 16 nuclei on the initial
preview plane, versus 8 among 16 on the 12-plane maximum projection. This
demonstrates an input discrepancy; it does not establish per-nucleus truth.

Fix this discrepancy before judging another detector by eye. Distinguish display
contrast from measurement thresholds: the current previews stretch contrast
independently, while measurements use the raw stored intensities.

### Threshold changes alone have failed the small PNC trade-off

The local HeLa inputs contain 10 negative, 17 positive, and 10 small-PNC fields.
The owner requested **30% tuning and 70% validation**. The existing split uses:

| Group | Tuning fields | Validation fields |
| --- | ---: | ---: |
| PNC negative | 3 | 7 |
| PNC positive | 5 | 12 |
| PNC small | 3 | 7 |
| Total | 11 | 26 |

A previous search over seven pixel cutoffs and 120 background-aware peak rules
selected a 100-pixel cutoff using tuning fields. Its held-out results were:

| Validation group | Legacy 10-pixel cutoff | Selected 100-pixel cutoff |
| --- | ---: | ---: |
| PNC negative | 24.6% | 0.3% |
| PNC positive | 84.7% | 73.7% |
| PNC small | 8.2% | 0.0% |

These are means of positive-call percentages per field, not sensitivity,
specificity, or accuracy. The selected cutoff was rejected because it lost all
small-PNC calls. The subsequent adaptive preview also produced excessive calls
in negative fields at permissive settings.

Do not reuse early adaptive reports' slider numbers as final operating points:
the preview's sensitivity mapping changed during development. Record the exact
algorithm, mapping, parameters, and source revision for each new comparison.

### Biological truth is not supplied by folder names

The folders identify sample groups, not verified labels for every nucleus or
punctum. Expected true-positive percentages, specimen relationships, and
acquisition comparability have not been confirmed. Some negative-group images
have higher raw intensity peaks than small-PNC images. A shared absolute
brightness cutoff is therefore not sufficient evidence of PNC identity.

The existing holdout results have already been inspected during development.
Further comparisons on them must be labeled exploratory; independent accuracy
claims require fresh fields or genuinely unused specimen groups.

## User workflow

1. Add images or drag in a folder. See a labeled analysis-consistent preview.
2. Run nucleus detection once. Obtain PNC candidates and an initial result
   without providing training examples.
3. Open **Adjust PNC sensitivity**. Move the slider from **Stricter** toward
   **More sensitive**, with a live overlay and count update.
4. Inspect the marker image, candidate boundaries, and relevant Z evidence.
   Display contrast controls must not change the measured calls.
5. Save a new revision or use the PNC settings for subsequent analyses.
   Preserve original results and any explicit manual PNC overrides.

Opening an existing analysis must continue to work without SAM or raw files.
If Z-aware scoring needs unavailable raw data, offer the documented 2D fallback
and clearly label it. Do not imply that old projection-only exports contain Z
evidence.

## Required behavior

### R1 Consistent preview and measurement

- Default the main analysis preview to the same selected acquisition and
  representation used for scoring. Loading a consistent preview may happen in
  the background and use the projection cache.
- Label channel mapping, time, position, and representation, such as maximum
  projection or a specific Z-plane. Clearly distinguish candidate evidence views.
- Provide raw-marker and detection-overlay views with synchronized navigation.
- If single-plane inspection is available, moving the Z viewer must not silently
  change the scoring protocol or saved calls.
- Offer an easy way to compare display contrast across images. Auto-contrast
  remains display-only and must not rescale the underlying measurements.

### R2 Training-free candidate detection and scoring

Evaluate a small, predefined shortlist using the tuning fields. Suitable options
include multiscale LoG/DoG candidate detection, robust local prominence above
nucleoplasmic background, and morphology-based artifact rejection. Reuse or
replace the current top-hat/MAD implementation based on evidence.

The method must:

- Use background estimates around the candidate and within its nucleus, with
  candidate signal excluded from the background reference where practical.
- Combine meaningful contrast with noise-relative evidence. A tiny estimated
  noise denominator must not turn negligible variation into a strong call.
- Use calibrated physical dimensions when available. Retain documented pixel
  fallbacks and never invent a physical scale from image appearance.
- Distinguish candidate strength from the number of bright pixels. Size, spatial
  support, and plausible structure should contribute to rejection of isolated
  noise, diffuse staining, hot pixels, and boundary artifacts.
- Preserve small/weak puncta as an explicit challenge. Do not require every PNC
  to be large or circular; do not solve negative controls by eliminating small PNCs.
- Address the chance of incidental detections when a nucleus contains many
  candidate peaks. One arbitrary bright pixel or weak peak must not suffice.
- Produce explicit reasons or review flags for problematic detections, including
  boundary artifacts, uncertain scale, or saturation when identifiable.
- Use only image measurements and the chosen protocol to score a sample.
  Folder name, filename, and knowledge that an image is in the tuning or
  validation set must never enter the detector.

These requirements describe the decision rule, not a promise that a particular
filter will meet the biological target. Reject unsuccessful candidates and report
the trade-off instead of adopting the best of several inadequate options.

### R3 Use Z evidence without a new 3D segmentation system

For Z-stacks, test whether per-plane local background and candidate focus or
continuity improve discrimination over maximum projection alone. Keep nucleus
segmentation unchanged for the comparison.

- Preserve the Z-plane source of candidate evidence when available. A projected
  noise maximum must not automatically be treated as a coherent punctum.
- Do not impose a universal requirement that a spot appear in two or more slices.
  Slice spacing and genuinely small structures can make that rule inappropriate.
- Single-plane TIFFs and projection-only saved analyses must remain supported.
- Stream planes or cache compact evidence. Do not require a full floating-point
  Z-stack in GPU memory or save every raw stack in every review revision.
- If Z evidence is added to caches or exports, version it and invalidate caches
  when the source, channel/time/position selection, Z policy, or relevant scoring
  algorithm changes. Read older analyses without silently changing their method.

### R4 One meaningful sensitivity slider

- Reuse the current review slider and asynchronous update controller.
- Retain the direction **Stricter → More sensitive** and a broad useful range.
- Keep candidate geometry and expensive image measurements stable while dragging.
  With other settings fixed, increasing sensitivity must not remove a previously
  accepted candidate through threshold-dependent merging or size filtering.
- Display the chosen value, method, live counts, and candidate overlay. Explain
  clearly whether changes are previewed, saved in a revision, or applied to future
  analyses.
- Preserve manual overrides. Do not treat a manual call as an automatically
  measured result in export provenance.
- Keep size limits, background controls, and Z-policy details under Advanced
  settings. A typical user should not need to tune several technical fields.
- Call the output a detector score or signal measure. Do not label it a calibrated
  probability or accuracy percentage without an appropriate calibration study.

### R5 Performance and dependencies

The new PNC measurement stage must run without a GPU and must not invoke SAM
when the slider moves or saved masks are remeasured.

For the supplied fields, approximately 1040 × 1392 pixels with tens of nuclei,
target cached slider responses below 0.5 seconds median and below 1 second at
the 95th percentile, including debounce and rendering. Target initial PNC feature
preparation within a few seconds per field. Record hardware, image dimensions,
and cold/warm-cache conditions rather than assuming these targets were met.

Keep Tk operations on the main thread. Use background work, debouncing,
cancellation/close handling, and request tokens so older results cannot overwrite
the latest slider position. Bound memory to the active field and compact cached
measurements where practical.

### R6 Reproducible and reversible results

Record method/version, operating threshold, sensitivity mapping, physical scale
or fallback, channel/time/position selection, projection/Z policy, candidate
measurements, and any review overrides. Save enough information to reopen a
revision consistently.

Preserve legacy results and defaults until the owner accepts a replacement.
Do not overwrite the batch's original counts or change old analyses on load.
Continue to use new review revisions for accepted edits.

## Validation plan

### Existing local resources

These inputs and outputs are private, ignored workspace files. They may be
absent from another checkout; inspect availability before running commands and
do not upload them to GitHub:

- Raw controls: `pnc_counting/testfiles/HeLa/PNC negative/`,
  `pnc_counting/testfiles/HeLa/PNC positive/`, and
  `pnc_counting/testfiles/HeLa/PNC small/`.
- Original negative/positive exports: `.venv/Scripts/results/` in this workspace.
- Small-PNC baseline exports:
  `validation/local/pnc-discrimination/small-baseline/`.
- Existing split and earlier frozen parameters:
  `validation/local/pnc-discrimination/heldout-30-70/`.

Compare the same retained nucleus geometry across PNC methods. Changing SAM
models, nucleus area cutoffs, or inclusion rules at the same time would confound
the comparison. Respect explicit manual overrides and report automatic calls
separately when evaluating a detector.

### Experiment discipline

1. Keep the owner's 30/70 split by whole field, with all groups represented.
   Group duplicate fields and related specimens together when that information
   becomes available. Do not split nuclei from one field across subsets.
2. State the candidate methods, tuning objective, and parameter search before
   comparing them. Use tuning fields only to select the operating point.
3. Freeze the selected method/configuration before evaluating the remaining
   fields. Do not search the validation results for a more favorable threshold.
4. Report per-field counts and group distributions with every denominator.
   Distinguish field-averaged percentages from pooled nucleus percentages.
5. Compare legacy, current adaptive preview, and proposed method using explicitly
   recorded versions and identical geometry.
6. Treat current-dataset follow-up results as exploratory because its holdout has
   been examined. Reserve fresh fields for stronger final generalization claims
   if they are available; do not block implementation on collecting them.

Folder-level call rates are diagnostic proxies. They cannot establish per-cell
false-positive rates, sensitivity, or accuracy without reviewed truth.

### Visual validation with little user effort

Provide side-by-side raw views, identical display settings, candidate overlays,
and relevant Z evidence for representative negative, clear-positive, and
small-PNC examples. Include failures and ambiguous cases, not only favorable
images.

An optional short check of roughly 10–20 representative nuclei can help confirm
the intended visual definition and expose obvious misses. It must not become a
mandatory training exercise. Do not fit a classifier on this feedback or require
the owner to annotate hundreds of nuclei to use the app.

### Automated regression tests

Cover at least:

- Initial preview and analysis representation/channel/time/position agreement.
- Constant, weak-noise, gradient-background, hot-pixel, and diffuse-signal images.
- Small/weak puncta, touching candidates, varying signal gain/offset, and varied
  calibrated pixel sizes.
- A coherent Z-localized punctum and an isolated projected noise peak, including
  coarse Z spacing and single-plane fallback behavior.
- Empty/rejected nuclei, border rules, stable assignment, and manual overrides.
- Monotonic candidate acceptance across the slider, rapid updates, stale-response
  rejection, and no SAM invocation during remeasurement.
- Geometry edits invalidating affected measurements, while sensitivity changes
  reuse prepared features.
- Save/reopen parity, legacy result compatibility, method provenance, and cache
  invalidation after relevant acquisition or algorithm changes.
- Preview installer/profile isolation and rejection of development versions by
  stable release guards.

## Acceptance criteria

| Area | Acceptance condition |
| --- | --- |
| No training requirement | A user can analyze and adjust PNC calls without labels, model fitting, or an extra model download. |
| Representation consistency | The displayed analysis input matches the representation used for scoring; any inspection-only plane or contrast change is clearly identified. |
| Negative-control separation | Show a reduction in unsupported negative-group calls at one frozen operating point, without hiding exclusions or moving nuclei out of the denominator. Do not assume every negative-folder nucleus is verified negative. |
| Positive and small PNC preservation | Demonstrate that the reduction is not achieved by removing visibly supported clear or small PNCs. Higher small-folder call rates alone do not prove improvement. |
| Live interaction | Meet the measured slider responsiveness targets or report the actual limitation and its cause. Retain stable geometry, manual calls, and latest-request behavior. |
| Compatibility | Existing tests and the added regressions pass. Original analyses remain readable and unchanged. |
| Delivery | Supply a local preview installer, source commit, checksums, test results, comparison report, and a short local-testing guide. |
| Release | The owner has tested locally and explicitly approved finalization. Only then may version/tag/publication work be proposed. |

Do not set an invented universal accuracy target from the folder labels. If a
method cannot satisfy the separation/preservation trade-off, deliver the failed
comparison and a bounded explanation. Do not call it an accuracy improvement.

## Implementation stages

1. **Fix representation consistency.** Reproduce the preview/projection discrepancy,
   correct or clearly separate the views, add regression tests, and retain a
   reproducible before/after example.
2. **Improve the training-free measurement.** Evaluate a short classical-method
   shortlist on tuning fields, address unstable noise normalization, and test Z
   evidence with a documented 2D fallback.
3. **Integrate the score.** Reuse the live slider, cached candidates, manual-call
   handling, protocol persistence, and immutable revision workflow.
4. **Validate and package.** Freeze the method, report exploratory control results
   and visual failure cases, run the relevant tests, and build a local preview.

Avoid broad GUI rewrites, changing nucleus segmentation, supervised training,
new cloud services, new acquisitions as a prerequisite, macOS work, or unrelated
release-workflow changes.

## Agent handoff instructions

Read this PRD and the current code before editing. Start by confirming the
working tree and any changes made after the code baseline. Preserve the owner's
files and existing published release.

Implement the prioritized training-free approach and reuse the v0.7 preview
infrastructure. Do not make an annotation campaign, learned classifier, or new
neural model a dependency. Do not claim accuracy from control-folder names or
synthetic tests. Record failures and all detector settings needed to reproduce
the comparison.

Commit locally in reviewable units. The owner has previously pushed through
GitHub Desktop; do not push or publish without authorization. Increment the
development preview version when making a new test build. Do not create a
v0.7.0 release tag or finalize the release until the owner explicitly approves
the locally tested result.

## References

- [Current README and preview instructions](../README.md).
- [Accuracy workflow](accuracy-workflow.md) and [manual review](manual-review.md).
- [Validation notes](validation.md) and [Windows installation guide](windows-installer.md).
- [Example biological PNC scoring definition](https://pmc.ncbi.nlm.nih.gov/articles/PMC2640956/):
  appearance, nucleoplasmic contrast, and perinucleolar location are relevant;
  this does not establish a universal numerical threshold for these images.

Open scientific questions for the local review are the expected small-PNC
prevalence, which negative-group structures the owner would reject, and whether
fields share specimens or acquisition settings. Use safe documented fallbacks
while these are unresolved; do not infer specimen independence or nucleolar
identity from filenames or DAPI-dark regions alone.
