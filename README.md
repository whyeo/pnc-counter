# Nucleus Analysis / PNC Counter

Python application for segmenting DAPI-labelled nuclei and counting PNC-positive
nuclei in Nikon ND2 and multichannel TIFF images. Includes a desktop app, batch
CLI, and Python API. No MATLAB, Java, Bio-Formats, pandas, or web server is needed.

**Accuracy status:** replaying the two existing MATLAB segmentations reproduces
the recorded counts exactly (67/76 and 42/45). SAM 2.1 is a new segmentation
backend and must be validated against reviewed masks before claiming improved
biological accuracy. See [validation](docs/validation.md).

## Install

### Windows installer (recommended for desktop users)

Double-click `PNC-Counter-0.6.0-Setup-x64.exe`. Python and the base image tools are
included. On first launch, the guided setup recommends CPU or NVIDIA GPU support,
installs PyTorch and official SAM 2.1 in a separate private environment, downloads
Tiny/Small weights, and tests real model inference before saving the setup.
Users do not need PowerShell, a system Python, Git or a compiler. Later launches
reuse the saved setup. **Set up / repair SAM** and a Start menu setup shortcut
reopen the wizard. See the [Windows installation guide](docs/windows-installer.md)
for downloads, prerequisites, repair, uninstall behavior, and build instructions.

### Python package / developer installation

Python 3.10+ is required (3.12+ for optional SAM 3). From this repository:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install .
```

On macOS/Linux activate with `source .venv/bin/activate`. Linux desktop users
may need their distribution's `python3-tk` package; headless use does not need Tk.

The base installation contains NumPy, SciPy, scikit-image, nd2, tifffile, and
Pillow, plus a small native Tk drag-and-drop wrapper. Deep-learning dependencies and model weights are separate so a small
installation can read images, analyze existing masks, and use watershed.

## SAM 2.1 setup (recommended)

SAM 2.1 Tiny is the default: an updated SAM model with a 156 MB checkpoint.
Install PyTorch for your hardware, then the pinned **official Meta SAM 2** source
and checkpoint:

```powershell
# CPU-only example; use the PyTorch installation selector for CUDA instead.
python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
python tools/setup_sam2.py --install --model tiny
```

The setup script requires Git for the source installation. Downloads happen only
when setup is explicitly run; analysis uses a local checkpoint and runs offline.
Weights stay in the ignored `models/` folder. A SHA-256 manifest is saved beside
the checkpoint. Small, Base Plus, and Large are also available through `--model`.
SAM 2's CUDA extension is disabled for portability; inference does not require
compiling native extensions. Meta recommends WSL for Windows; the Tiny backend
was also tested with native Windows CPU inference in this repository.

Two tested presets are provided: [Tiny/CPU](examples/sam2-tiny-cpu.json) for a
smaller model and [Small/CUDA](examples/sam2-small-cuda.json) for better boundary
agreement on the local examples. Import either JSON in the desktop app, or use
`--config examples/sam2-small-cuda.json` in the CLI. Small needs its own checkpoint
(`python tools/setup_sam2.py --model small`) and CUDA-enabled PyTorch.

SAM 3/3.1 is the newer family, but the official installation requires Python
3.12+, PyTorch 2.7+, a CUDA GPU, and access to its gated checkpoints. Its text-based
image segmentation is available experimentally through `--backend sam3`,
`--device cuda`, `--checkpoint path/to/sam3.pt`, and `--sam3-prompt "cell nucleus"`.
Install it in a separate environment following [Meta's instructions](https://github.com/facebookresearch/sam3).
Use the **SAM 3 image checkpoint**, not the SAM 3.1 video multiplex checkpoint;
the latter improves multi-object video tracking, which this 2D projection
workflow does not use. The adapter has not been validated on these images.

## Desktop app

```powershell
pnc-counter
# Equivalent:
python -m nucleus_analysis --gui
```

Add images, add a folder, or drag multiple images/folders onto the drop area,
table, or preview. Folders include nested acquisitions; duplicate paths and this
app's result directories are excluded. Filenames appear immediately, with blank
counts until each analysis completes. Select a row to see a raw channel preview,
then click **Analyze images**. Completed rows show the analysis overlay and can
be opened for correction. The separate Status column reports progress or errors.

The first launch checks usable CPU/CUDA/MPS hardware in the background and locates
the selected model. Setup, analysis preferences, output folder, and confirmed
channel mappings are saved in a versioned JSON preferences file. On Windows it is
`%LOCALAPPDATA%/PNC Counter/preferences.json`; macOS uses
`~/Library/Application Support/PNC Counter/`, Linux uses
`$XDG_CONFIG_HOME/PNC Counter/` (default `~/.config/PNC Counter/`). Subsequent launches
reuse the hardware profile without importing Torch. Changes to Python or runtime
package versions invalidate it automatically. After installing a driver or changing
hardware, use **Advanced settings → Redetect hardware**. Auto selects an available
accelerator while keeping the chosen segmentation model and scientific rules.

Obvious DAPI/PNC channel names can be identified automatically. Generic marker
names such as TxRED require an initial confirmation with thumbnails; **Check
channels** changes a saved mapping. Mapping signatures include channel names,
axis layout, channel count and time/position counts. Multi-time/position images
require an explicit initial selection; this version analyzes one selected time
and position. Preview contrast does not affect measured intensities. Physical
calibration comes from ND2/OME metadata when present; unknown scale is not guessed.

Technical settings, protocol JSON import/export, optional manual acquisition
indices, and verified Tiny/Small checkpoint downloads are under **Advanced
settings**. The Windows installer edition has **Set up / repair SAM** for the
one-time engine installation; Python/wheel users can use the manual instructions
above. Model downloads are explicit; analysis works offline.

The progress display shows finished images separately from the current step:
loading, finding nuclei, measuring PNC, and saving. Elapsed time updates while work
continues; a rough remaining-time estimate appears after the first file. **Stop
after this image** preserves finished results and retains unprocessed rows.
Changing PNC thresholds reuses both the projection cache and segmentation cache;
source path, size, modification time, reader version and channel/time/position
selection invalidate projections. Per-file failures are saved in `errors.json`.

### Correct nuclei manually

Select a completed result and click **Review / correct selected** (or double-click
the result). **Open saved analysis** reopens an original or reviewed
`analysis.json`, without reading raw ND2 files or loading SAM.

- Click to select a nucleus; Ctrl+click selects several. Zoom with the wheel,
  pan with the middle mouse button, and switch between DAPI/PNC/threshold views.
- **Add** outlines a missed nucleus. **Redraw** replaces the selected boundary.
  Click vertices or drag freehand, then press Enter to finish; Esc cancels.
- **Reject / exclude** removes an incorrect detection from the count but keeps
  it visible. **Flag for follow-up** highlights it yellow while keeping it counted.
  Accept restores a rejected nucleus; Delete removes its geometry from the review.
- **Split** outlines one part of a selected nucleus; the remaining pixels form
  the other part. **Merge** combines selected detections. Undo/redo and reset to
  the original are available.
- Counts update immediately. **Save new revision** writes corrected statistics,
  images, a label TIFF, and correction history in a new directory. The original
  analysis and its batch summary are preserved. Reopen the new `analysis.json`
  to continue reviewing later.

See the [review guide](docs/manual-review.md) for overlap rules, stable IDs,
keyboard shortcuts, and saved-file details. Proposed next improvements are
prioritized in the [roadmap](docs/roadmap.md).

### Accuracy workflow and additional analysis modes (v0.4)

- **Advanced settings → Nuclei / PNC / Acquisition** includes explicit border exclusion, nucleus area
  in µm² from ND2/OME calibration or manual pixel sizes, and a separate candidate
  PNC spot mode. Default pixel counting is unchanged.
- The sidebar now prioritizes uncertain/unreviewed/flagged objects and records
  notes, reviewer names, verified status, and manual PNC calls.
- **Add verified reference** registers completed reviews into grouped
  validation/test sets. `nucleus-benchmark` reports instance/PNC F1/IoU and
  count/percentage errors with source hashes.

See the [accuracy workflow guide](docs/accuracy-workflow.md) for definitions,
examples, and validation limits. Reference sets require explicit human review;
model-produced masks are not automatically treated as ground truth.

## Batch analysis

```powershell
python -m nucleus_analysis "data" --recursive --checkpoint models/sam2.1_hiera_tiny.pt --output results --cache results/cache

# Explicit lightweight alternative, with no model or PyTorch:
python -m nucleus_analysis "data" --backend watershed --output results

# Replay a saved MATLAB segmentation to check migration parity:
python -m nucleus_analysis "IMG1.nd2" --masks "IMG1_segmentation.mat" --output results

# Save settings without processing; all fields are available via CLI or JSON:
python -m nucleus_analysis --save-config settings.json
python -m nucleus_analysis "data" --config settings.json --checkpoint models/sam2.1_hiera_tiny.pt
```

Each image gets its own output directory (including a path-derived suffix to
avoid collisions between identical names in different folders):

| Output | Contents |
| --- | --- |
| `summary.csv` (batch root) | Positive, negative, rejected, total, percentage, output path |
| `errors.json` (batch root) | Failed files and error messages; CLI exits nonzero if any fail |
| `nuclei.csv` | Per-nucleus shape, intensity, centroid, positive-pixel count, classification |
| `analysis.json` | Effective settings, input metadata, backend/import provenance, counts |
| `images.npz` | Projections, threshold image, and numbered classification masks |
| `nuclei_masks.npz` | Exact retained candidate geometry, including overlaps, for review/replay |
| `visualization.png` | DAPI, numbered/classified nuclei, raw PNC, thresholded PNC |

Only one input image and its candidate masks are retained at a time; ND2 stacks
are projected in two streaming passes. Candidate masks are stored as sparse pixel
indices rather than full-frame binary arrays. Caches use projection content,
checkpoint content, and segmentation settings, so PNC threshold adjustments can
reuse masks safely. Explicit `--masks` import records its source and checks shape;
the user is responsible for choosing masks belonging to that image.

## Analysis conventions

- Default channels: DAPI 0, PNC 1 (zero-based). Override with `--dapi-channel` and
  `--pnc-channel`. Channel names are recorded for ND2, never guessed.
- DAPI maximum projection is used for segmentation, quantized DAPI mean for
  measurements, and PNC maximum for positivity, matching the MATLAB GUI.
- Default nucleus area: 5,000–50,000 pixels; positive nucleus: at least 10
  thresholded PNC pixels. These are dataset-specific **pixel** values, not physical
  area or a count of individual PNC puncta. Match magnification/pixel size or tune
  them for another acquisition.
- Local Gaussian threshold defaults to the old GUI's setting 90, neighborhood 21.
  Its Gaussian sigma and integer intensity scaling reproduce MATLAB `adaptthresh`.
  Global mode preserves the original median-based formula; its old GUI setting
  was 70, so use `--threshold-mode global --image-threshold 70` for that preset.
  Local mode expects floating-point PNC inputs in [0, 1]; integer inputs use
  their dtype's full scale (e.g. 65,535 for uint16), matching MATLAB.
- The old headless script differed from the GUI: positivity 30, neighborhood 7,
  and SVM rejection enabled. Use `--positive-threshold 30 --neighborhood-size 7
  --quality-filter legacy-svm` to select those conventions.
- The legacy GUI defined an SVM loader but never called it. The Python default
  therefore has `--quality-filter none`. The converted SVM is optional and needs
  no scikit-learn. Its shape features may be inappropriate for a new model or
  acquisition; review rejected masks before adopting it.
- Centroids are one-based X/Y pixel coordinates to match MATLAB tables. Labels
  are unsigned 32-bit integers. Empty fields report percentage `null`/blank,
  rather than division by zero.
- Z is projected. T (time) and P (position) are selected explicitly, default 0,
  using `--time-index` and `--position-index`. Each invocation analyzes one
  selection per file. Unsupported nonsingleton axes are rejected. TIFF must have
  C/Y/X axes; use `--axes ZCYX` when metadata is ambiguous. RGB is not interpreted
  as multichannel microscopy automatically.
- Overlap suppression preserves the old small-mask-first, >10% overlap rule.
  Tied intensity percentile features use finite empirical ranks; these unused
  SVM features intentionally differ from MATLAB's brittle repeated quantile bins.

## Python API

```python
from nucleus_analysis import AnalysisConfig, count_pnc

config = AnalysisConfig(checkpoint="models/sam2.1_hiera_tiny.pt")
result = count_pnc("sample.nd2", config=config)
print(result.basic_stats)
for nucleus in result.full_stats:
    print(nucleus["MaskID"], nucleus["NumberCh2PixelsPositive"])

# Saved masks can also be analyzed without loading a model:
result = count_pnc("sample.nd2", masks="sample_segmentation.mat")
```

`analyze(Projections(...), config, masks=...)` supports in-memory images. Candidate
masks use row-major, zero-based flat pixel indices; `load_masks` converts the
one-based, column-major indices in old MATLAB caches automatically.

## Test and distribute

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests tools
python -m build
python -m pip install dist/nucleus_analysis-0.6.0-py3-none-any.whl
```

The wheel contains only Python code and the small exported SVM, with no raw data,
MATLAB code, JVM, neural weights, or bundled PyTorch. Distribute it with the
appropriate dependencies and a separately downloaded checkpoint for offline use.
The repository also builds a Windows installer with a private Python runtime:
`python tools/build_windows.py --bootstrap-compiler`. A manually triggered
**Windows installer** GitHub Actions workflow builds the same installer.
CI tests the base package on Windows/Linux with Python 3.10/3.12; real microscopy
data tests skip when private local data are absent. The Windows installer is
unsigned; code signing and a separate clean Windows machine test remain release steps.

The original implementation is preserved in [legacy/matlab](legacy/matlab) for
historical comparison. [Migration notes](docs/migration.md) describe deliberate
differences and the one-time MATLAB export tool. Runtime workflows are Python-only.

## License

Application code is [MIT licensed](LICENSE). SAM models, code, PyTorch, and other
dependencies retain their own licenses; consult Meta's terms when redistributing
weights. See [CHANGELOG](CHANGELOG.md).
