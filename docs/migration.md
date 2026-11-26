# MATLAB to Python migration

The supported application is now `src/nucleus_analysis`. The old app, headless
function, trained model, and Bio-Formats distribution are preserved under
`legacy/matlab` and are excluded from Python distributions.

| MATLAB | Python |
| --- | --- |
| `pncCounter` | `pnc-counter` or `python -m nucleus_analysis --gui` |
| `headless/count_pnc.m` | `nucleus_analysis.count_pnc` or batch CLI |
| Bio-Formats + Java ND2 reader | `nd2`, with metadata-based axes and streaming projection |
| `imsegsam` | Official SAM 2.1 automatic mask generator; optional SAM 3 image adapter |
| MATLAB tables | Lists of per-nucleus dictionaries and CSV |
| `.mat` segmentation cache | Content-addressed NPZ; old `.mat` caches importable |
| `.mat` ClassificationSVM | Small JSON model, evaluated with NumPy |
| `labeloverlay` / figures | Pillow PNG panels and label arrays in NPZ |

## Preserved behavior

Projection/rounding, Gaussian PNC thresholding, positive-pixel counts, area
ordering, overlap suppression, smoothing IoU, circularity's corrected digital
perimeter, sample standard deviation, Hazen IQR, one-based centroids, and the
optional SVM's **two** standardization stages were carried over. Directly
evaluating only Beta/Bias without the second standardization would change the
classifier. The exported model is linear and requires no MATLAB or scikit-learn.

The legacy app and headless function had different defaults. Python defaults
follow the app (10 positive pixels, Gaussian setting 90/neighborhood 21, no SVM).
Although the app defines `loadSVMModel`, it never invokes it; silently enabling
that classifier would change published counts. Global threshold mode's legacy
setting was 70; switching modes in Python does not silently change a numeric
setting, so select it explicitly.

## Deliberate differences and limitations

- A model failure is reported; SAM never falls back to watershed silently.
- Constant images have finite projections; empty analyses have undefined
  percentage (`null`) rather than NaN/Inf.
- Tied intensity ranks use an empirical cumulative distribution rather than
  repeated percentile bin edges. These columns are not used by the existing SVM.
- Solidity uses scikit-image's convex-hull rasterization. On the two local
  reference images its maximum absolute difference from MATLAB is 0.002763.
  This caused zero SVM classification changes on their accepted masks, but is
  not a guarantee for masks near the decision boundary.
- SAM 2.1 produces different candidates from the old SAM. Baseline replay proves
  the measurements/counting port, not accuracy of a newly chosen segmentation
  model. SAM 3 image inference is an experimental adapter and has not been run
  in the Python 3.10/CPU validation environment. SAM 3.1 video multiplex weights
  are not interchangeable with SAM 3 image weights.
- The app is a 2D projection workflow. True 3D segmentation, temporal tracking,
  physical-unit thresholds, automatic channel identification, and model training
  are not implemented. Native Windows CPU SAM 2.1 was tested; CUDA/MPS and Linux
  model inference require validation on their target hardware.
- GPU model runs can vary slightly at mask boundaries; the validation notes
  report this separately from the exact counting/projection replay checks.
  Reuse saved candidate masks when comparing PNC thresholds.

## Reproduce the independent MATLAB comparison

Only a developer re-exporting the historical reference needs MATLAB. From the
repository root with the original local ND2 test data present:

```powershell
matlab -batch "run('tools/export_matlab_reference.m')"
python tools/validate_baseline.py
```

The export tool reads images through the original Bio-Formats reader and
calculates independent projections, thresholded pixels, and measurements. It
exports the SVM to `src/nucleus_analysis/data/legacy_svm.json`, 100 deterministic
feature/prediction/score pairs to `tests/fixtures/legacy_svm_vectors.json`, and
private image references under ignored `validation/local`. Normal tests and
application use never launch MATLAB.

The original positive/negative image groups are not manual nucleus annotations.
Do not treat those folder names or SAM-produced masks as biological ground truth.
