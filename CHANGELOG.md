# Changelog

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
