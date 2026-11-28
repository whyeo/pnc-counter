# PNC Counter

PNC Counter is a Python desktop application for finding nuclei and counting cells
with perinucleolar compartments (PNCs) in Nikon ND2 and multichannel TIFF images.
SAM finds the nucleus boundaries; **local enrichment** measures candidate PNC
brightness relative to the surrounding nucleoplasm.

**Current revision: 0.7.0.dev6, the v0.7.0 local preview.** The default local enrichment threshold
is **1.8x**. Automatic calls are a starting point for human review. This preview
must be tested locally before its release is finalized.

This README describes the current revision. Version history is in the
[changelog](CHANGELOG.md).

## Analyze and review images

1. Open **PNC Counter** and complete image-engine setup if prompted.
2. Drag in images or a folder, or use **Add images** / **Add folder**. Filenames
   appear immediately; counts appear when processing finishes.
3. Check the DAPI and PNC channel previews and the selected time and position.
   Generic channel names may need a one-time confirmation.
4. Choose the output folder and click **Analyze images**.
5. Open a completed analysis to inspect nuclei, candidate PNCs and automatic calls.
   Adjust the local enrichment threshold, correct individual calls as needed,
   then **Save review** to create a new revision.

The input preview and analysis use the same selected maximum projection. Display
contrast only changes what you see; it does not change measured intensities.
Technical model, acquisition, calibration and protocol settings are under
**Advanced settings**.

## Adjust the local enrichment threshold

The review window provides a **Local enrichment threshold** slider and a numeric
fold-enrichment value. The default is **1.80x**.

| Adjustment | Expected effect |
| --- | --- |
| Lower the threshold | More sensitive; more candidates and cells may be called PNC-positive. |
| Raise the threshold | Stricter; fewer candidates and cells are called PNC-positive. |
| Reset to 1.8x | Restore the default threshold. |

The method compares the median raw intensity in a candidate's central **3x3 pixel
neighborhood** with the median intensity in a surrounding reference ring inside
its nucleus. A cell is automatically PNC-positive when at least one eligible
candidate reaches the selected threshold. Physical image calibration is used
when available; fallback scale and reference-support warnings are recorded.

Threshold adjustments reuse prepared measurements and nucleus geometry. They do
not rerun SAM. Counts and overlays update after a short pause. Review flagged
references and incidental bright structures before accepting the counts.

**Advanced → Use for next analysis** reuses the selected PNC protocol for subsequent images.
The method and threshold are recorded with saved results. Reopening an older
analysis preserves its stored protocol until you explicitly change it. Existing
preferences also retain the selected protocol; choose **Local enrichment** and
**Use for next analysis** to switch an existing setup to the new method.

## Correct individual results

Open **Review results** or **Open saved analysis**. Saved analyses can
be reviewed using their stored images and masks without loading SAM or the
original ND2 file.

- Select a nucleus to inspect its automatic call and any review flags.
- The fixed side panel keeps **PNC+**, **PNC−**, **Auto**, **Exclude nucleus**,
  and **Checked & next** visible. Exclusion removes an unsuitable segmentation
  from the counts; a PNC-negative nucleus remains in the denominator.
- Set a manual positive or negative PNC call when you disagree. Manual overrides
  take precedence over automatic threshold changes.
- Add a missed nucleus, redraw an incorrect boundary, split touching nuclei,
  merge fragments, or reject an unsuitable detection. Undo and redo are available.
- Save a **new revision** to preserve the original analysis, reviewed geometry,
  threshold, manual decisions and correction history.

**Add nucleus**, **Edit outline** and **Undo** stay above the image. Finish/Cancel
appear while drawing. Split, merge, delete, notes and flags are under **More
actions**; method settings and technical diagnostics are under **Advanced**.

Nuclei are numbered left to right within approximate rows, then top to bottom.
Display numbers and internal mask IDs are mapped in every export. Threshold,
PNC-call and exclusion changes do not renumber nuclei. Geometry edits can change
the spatial order; the mapping is saved separately for each revision.

See the [manual review guide](docs/manual-review.md) for geometry-editing tools
and saved-file details.

## Install and launch from source

The base application requires **Python 3.10 or later**. New-image SAM analysis
also requires a compatible PyTorch/SAM engine and downloaded model weights.

Windows PowerShell, from this repository:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\pnc-counter.exe
```

On macOS/Linux, use the corresponding `.venv/bin/python` and
`.venv/bin/pnc-counter` commands. Linux desktop installations may require the
system's Tk package. A packaged macOS application is not provided.

The base package uses NumPy, SciPy, scikit-image, nd2, tifffile, Pillow and
Tkinter. Deep-learning packages and model weights are separate. CPU-only use is
supported; a compatible accelerator can speed up nucleus segmentation.

### Set up SAM for a source installation

SAM 2.1 Tiny is the default nucleus model. The following is the project's pinned
CPU setup example for a compatible Python environment:

```powershell
.venv\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe tools/setup_sam2.py --install --model tiny
```

The setup script installs the official SAM 2 source and downloads the selected
checkpoint; Git is required for this source-install route. For NVIDIA use a
compatible CUDA-enabled PyTorch installation. Models are stored locally, and
analysis can run offline after setup. Keep the same nucleus model when comparing
PNC thresholds.

Hardware detection and preferences are cached between launches. Use
**Advanced settings** to redetect hardware or change the model after a driver or
hardware update. Development builds use a separate **PNC Counter Preview**
preferences profile.

### Windows setup builds

A setup executable includes the base Python application. Its first-run wizard
installs the analysis engine and verifies the selected model. Users of such a
build can follow its guided setup instead of the source commands above.

The current v0.7 preview is awaiting local acceptance; this README does not link
to an unreleased installer. See the [Windows build guide](docs/windows-installer.md)
for packaging and setup details.

## Batch command line

The command-line interface uses the same analysis settings as the desktop app.
Run `nucleus-analysis --help` for all options. Example with an installed SAM
checkpoint:

```powershell
nucleus-analysis path/to/images --recursive --output results --backend sam2 --sam2-model tiny --checkpoint models/sam2.1_hiera_tiny.pt --device cpu --pnc-mode enrichment --pnc-enrichment-threshold 1.8
```

Export or import a protocol JSON when you need to reuse the same method,
threshold and acquisition settings across a batch.

## Results

Each image has its own results directory. Outputs include:

| Output | Purpose |
| --- | --- |
| `nuclei.csv` | Per-nucleus measurements, automatic calls and review information. |
| `nucleus_numbering.csv` | Spatial display number → persistent mask ID, row and centroid. |
| `spots.csv` | Candidate PNC measurements when produced by the selected method. |
| `visualization.png` | Image overlays for checking the analysis. |
| `analysis.json` | Saved configuration and provenance used when reopening the analysis. |
| Saved images and nucleus masks | Reproducible review and remeasurement without rerunning segmentation. |

Batch results also include a summary; failed inputs are recorded separately.
Reviewed revisions are saved in new directories rather than overwriting original
results.

## Interpretation

The 1.8x threshold is an adjustable starting point for human-vetted counts, not a
calibrated probability or a claim of 95% accuracy. Bright artifacts, structured
staining, weak signal, saturation and inadequate local references can affect
calls. Review both positive and negative examples and inspect the corresponding
raw images. Sample-folder names do not establish the identity of every cell.

Changing the PNC threshold does not repair an incorrect nucleus boundary. Review
segmentation and PNC calls as separate decisions.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

The [progress tracker](docs/v070-progress.md) records implementation and local
acceptance status. Historical changes and experiments belong in
[CHANGELOG.md](CHANGELOG.md), rather than this usage guide.

## License

[MIT](LICENSE).
