# Changelog

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
