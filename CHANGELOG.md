# Changelog

## v0.7.0 — 28 November 2026

- Counts PNC-positive cells using adjustable local enrichment, starting at 1.8x
  surrounding nuclear background. A live threshold slider reuses saved nuclei.
- Simplifies review with a fixed side panel, automatic image fit, spatially
  ordered nucleus numbers, manual PNC calls and immutable saved revisions.
- Adds installer upgrade/repair detection while preserving settings, models and
  results. Exports include number-to-mask-ID mappings and recorded thresholds.

Existing analysis protocols remain readable and retain their selected method.
Automatic calls require human review; no measured 95% accuracy claim is made.

## v0.7.0 installer maintenance preview (0.7.0.dev7, unreleased)

- Detects an existing installation of the same edition and asks to upgrade an
  older version or repair the same version. Cancel leaves app files unchanged.
- Reuses the registered folder, preserves settings/models/results, and prevents
  replacing a newer version with an older installer. Preview and stable remain
  separate; application-file repair is distinct from SAM-engine repair.
- Adds isolated, real-installer checks for fresh install, upgrade/repair prompts,
  cancellation, custom paths, damaged-file recovery and downgrade protection.
- Retains dev6 analysis, threshold and review UI; final release remains pending.

## v0.7.0 review interface preview (0.7.0.dev6, unreleased)

- Packages the local preview with current installation/review guides and
  changelog, plus versioned checksums and build provenance. Prior previews are
  preserved; this does not finalize or publish v0.7.0.
- Fits the image automatically when review first opens, while preserving later
  user zoom. Enlarges main-window buttons and anchors sensitivity captions to
  the slider's left and right ends.
- Replaces the scrolling review sidebar with a fixed native Python side panel.
  PNC calls, exclusion, review navigation and Save remain visible. The threshold
  sits above the image; drawing actions appear only while outlining.
- Moves notes, split/merge/delete, flags and less-used settings into More actions
  and Advanced. Combines the duplicate main-window review buttons.
- Formats the enrichment entry to two decimal places, including slider changes.
- Numbers nuclei left to right across approximate rows. Persistent mask IDs,
  annotations and label arrays remain unchanged. Exports include DisplayNumber
  and a per-revision nucleus_numbering.csv mapping; geometry edits may renumber.
- Retains dev5 detection/scoring, the 1.8x default, manual overrides and immutable
  revisions. Local preview only; owner testing is required before finalization.

## v0.7.0 local enrichment preview (0.7.0.dev5, unreleased)

- Makes local enrichment, initially 1.8x, the PNC protocol for new analyses.
  Candidate raw 3x3 intensity is compared with a reference ring within its nucleus.
- Adds a fold-enrichment threshold slider for live review, with a numeric readout
  and a reset to the default. Cached measurements allow threshold changes without
  rerunning nucleus segmentation.
- Retains explicit manual PNC overrides, stored protocols and immutable review
  revisions. Existing analyses retain their original method until changed.
- Keeps nucleus segmentation and PNC classification separate; local reference and
  spatial-support warnings assist human review. No measured 95% accuracy claim.
- Replaces the historical README narrative with a usage guide for the current
  revision. Earlier releases and research checkpoints remain in this changelog
  and the linked documentation.
- Local preview only. Owner interface testing and explicit finalization are
  required before a stable v0.7.0 release.

## v0.7.0 source exploration (0.7.0.dev3 / 0.7.0.dev4, not finalized)

- Added exact dev2 candidate-loss instrumentation and bounded, one-factor ablations.
- Added a new immutable 60/40 development/validation manifest with acquisition
  metadata, unchanged SAM geometry, source/export hashes and dev2 artifact protection.
- Added research-only enrichment measurements, permissive connected support,
  optional strictly compatible development-control profiles and one/two-component
  intensity-mixture diagnostics with explicit fallbacks. No new dependency is required.
- Preserved the failed dev3 threshold range; made one development-only dev4 range
  correction before validation, with candidate preparation unchanged.
- Reported paired versioned BEFORE/AFTER curves, denominators, losses and visual
  failures. The new frozen points increase negative-group calls; no replacement is
  adopted. Calibration lacked compatible replicated controls for validation.
- Existing live review, protocols, overrides and immutable revisions remain
  unchanged. No dev3/dev4 installer, stable tag or publication was created.
- See [the versioned exploration report](docs/v070-enrichment-exploration.md).

## v0.7.0 development preview (0.7.0.dev2, not finalized)

- Initial channel previews now use the same selected maximum Z projection as
  analysis, with channel/time/position labels and a shared marker display range.
- Added an optional multiscale prominence protocol with bounded noise scores,
  local/nuclear background, spatial support, multiplicity correction and review flags.
- Added compact streamed per-plane evidence, inspection of candidate source planes,
  an explicit projection fallback, cache versioning and self-contained revision exports.
- Retained the legacy default: the predefined HeLa comparison failed to preserve
  positive and small-PNC signals while suppressing negative-group calls. No accuracy
  improvement is claimed. See [preview testing and limitations](docs/v070-preview.md).
- Development preview only. Owner testing and explicit approval are still required
  before finalization, a stable tag or publication.

## v0.7.0 development preview (0.7.0.dev1, not finalized)

- Added an optional intranuclear background/noise-aware PNC candidate detector,
  with cached score images, fixed candidate geometry, and a broad sensitivity range.
- Added a debounced live sensitivity slider in the review window, stale-response
  protection, reusable batch PNC settings, and an Adjust PNC sensitivity entry point.
- Preserved manual PNC calls, undo/redo, immutable revisions, legacy defaults,
  and saved/exported method/score provenance. Slider changes do not rerun SAM.
- Added a separate local preview installer/profile and guards preventing development
  versions from being published through the stable release workflow.
- Biological accuracy remains unconfirmed; local user testing is required before
  v0.7.0 is finalized, tagged, or published.

## Windows installer and guided setup (v0.6.0)

- Added source-commit build provenance, release checksums and version-tagged
  GitHub assets, gated on an installed-app ND2 export check without MATLAB.

- Added a per-user Windows Setup executable with private portable Python/Tk,
  Start menu/optional desktop shortcuts, and an uninstaller that preserves user data.
- Added a first-run wizard for CPU/NVIDIA selection, PyTorch installation, bundled
  official SAM 2.1, verified model downloads and actual model-inference checks.
- Isolated analysis engines from the base app and other Python installations;
  failed/cancelled installations preserve the working setup and can be retried.
- Added setup logs, driver rechecks/download guidance, Windows runtime help and
  setup/repair entry points. Subsequent launches use the verified saved environment.
- Added pinned builder downloads, scientific version constraints, package manifests,
  setup regression tests and a manual Windows installer CI workflow.

## Simpler desktop workflow (v0.5.0)

- Added native file/folder drops, additive selection, recursive discovery and duplicate exclusion.
- Fixed filename rows appearing only after analysis; stable rows now have separate status and result columns.
- Added raw channel previews, conservative metadata suggestions and remembered acquisition confirmations.
- Moved technical options into Advanced settings, with protocol import/export and explicit acquisition overrides.
- Added background hardware checks, saved setup/preferences, automatic accelerator selection and hardware redetection.
- Added verified model downloads and local model discovery without silently switching scientific settings.
- Added named processing stages, finished-image progress, live elapsed/estimated time and retained cancelled rows.
- Cached projections as well as masks to speed repeat measurements; added desktop selection/setup/batch regressions.
- Fixed ND2 raw-preview ownership so frame pixels remain valid after closing the memory-mapped reader.

## Accuracy and analysis workflows (v0.4.0)

- Added verified reference registration, group-separated validation/test sets,
  content-matched prediction discovery, and end-to-end instance/PNC benchmarks.
- Added physical nucleus-area bounds, ND2/OME calibration, X/Y pixel-size overrides,
  explicit border rules, and physical-area exports.
- Added prioritized review queues, notes, reviewer identity, confirmation state,
  empty-field confirmation, and manual PNC overrides.
- Added opt-in candidate spot counting with touching-object splitting, size
  filtering, background subtraction, unique nucleus assignment, and exports.
- Preserved default MATLAB-compatible counts and reading of schema-1 reviews;
  new reviews use checksummed schema 2.

## Manual review (v0.3.0)

- Added nucleus selection, polygon/freehand add and redraw, rejection/restoration,
  follow-up flags, deletion, split/merge, undo/redo, and reset to original.
- Added zoom/pan, DAPI/PNC/threshold views, stable IDs, and immediate count updates.
- Added background revision saving, corrected measurements and review highlights,
  portable uint32 label TIFFs, checksummed review state, and preserved original masks.
- Added reopening of original/saved results without SAM or raw image files, a
  headless review API, functional Tk smoke tests, and review behavior tests.
- Documented review conventions and prioritized proposed accuracy/usability work.

## Python migration (v0.2.0)

- Added a Python-only package, batch CLI, and Tk desktop interface.
- Added official SAM 2.1 Tiny/Small/Base Plus/Large integration, an experimental
  SAM 3 image adapter, and an explicit model-free watershed alternative.
- Replaced Java/Bio-Formats runtime reading with streamed ND2 projection and
  axis-aware TIFF support.
- Ported measurements, PNC thresholding, counting, and linear SVM inference;
  reproduced both existing MATLAB GUI count examples exactly using cached masks.
- Added CSV/JSON/NPZ exports, review images, portable segmentation caches,
  settings import/export, baseline comparison tools, tests, and Python CI.
- Preserved original MATLAB sources and model under `legacy/matlab`.

## Initial Release (v0.1.0)

### Added
- Initial creation of the `CHANGELOG.md` file.
- Basic structure for documenting changes in the project.

### Fixed
- N/A

### Changed
- N/A

### Removed
- N/A
