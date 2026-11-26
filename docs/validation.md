# Validation evidence and model comparison

Validation was run on Windows, Python 3.10, using the local ND2 examples already
present in the repository's ignored test-data folder. These are regression
examples, **not independent manually annotated ground truth**.

## Counting and measurement baseline

The original recorded GUI results are in the local `results.csv`. Replaying its
saved SAM masks through Python produces:

| Image | MATLAB positive / total | Python positive / total | Percentage |
| --- | --- | --- | --- |
| IMG1 | 67 / 76 | 67 / 76 | 88.1579% |
| IMG2 | 42 / 45 | 42 / 45 | 93.3333% |

An independent MATLAB run used the original Bio-Formats reader and functions.
For both images, DAPI max, DAPI mean, and PNC max projections matched Python
exactly. The entire local PNC threshold image also matched: **zero differing
pixels**. Areas and per-mask positive-pixel counts matched exactly. Centroids,
circularity, smoothing IoU, eccentricity, and maximum-intensity measurements
agreed within 1e-9 absolute error.

Solidity has a known convex-hull rasterization difference: maximum absolute
error 0.002763. Applying the exported classifier to the MATLAB and Python
feature rows changed zero predictions on these 121 accepted baseline masks.
The linear SVM itself was tested on 100 deterministic feature vectors: all
predicted classes agree with MATLAB; score error is below 1e-12.

## Updated model: SAM 2.1 Tiny

Official Meta source revision `2b90b9f5ceec907a1c18123530e92e794ad901a4`;
checkpoint SHA-256
`7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`.
The checkpoint is 156,008,466 bytes. Initial inference used native Windows CPU,
PyTorch 2.5.1, 32 × 32 prompts, predicted-IoU threshold 0.7, stability threshold
0.95, area 5,000–50,000, overlap 0.1, and no SVM rejection.

| Image | MATLAB positive / total | SAM 2.1 Tiny positive / total | Matched instances at IoU ≥ 0.5 | Mean matched IoU |
| --- | --- | --- | --- | --- |
| IMG1 | 67 / 76 | 67 / 74 | 74 of 76; no unmatched predictions | 0.978500 |
| IMG2 | 42 / 45 | 42 / 45 | 45 of 45; no unmatched predictions | 0.979009 |

The PNC-positive counts agree. The first image has two unmatched legacy nuclei
and its percentage therefore changes from 88.16% to 90.54%. These results show
strong **agreement**, not proven improvement. Matching uses one-to-one instance
assignment, maximizing above-threshold matches before total IoU. It penalizes
missing, duplicate, split, and merged instances.

SAM 3's text-prompt adapter is experimental. It has not been executed in the
Python 3.10 validation environment; checkpoint access and a separate supported
environment are required. It must not be presented as a validated upgrade.

## Larger model and prompt-density experiments

SAM 2.1 Small (checkpoint 184 MB, SHA-256
`6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38`)
was tested with the same 32 × 32 sampling and thresholds on an NVIDIA RTX 5060 Ti
(16 GB), PyTorch 2.7.1/CUDA 12.8:

| Image | Small positive / total | Matched instances | Mean matched IoU |
| --- | --- | --- | --- |
| IMG1 | 67 / 74 | 74 / 76 | 0.982867 |
| IMG2 | 42 / 45 | 45 / 45 | 0.986739 |

The Small run, including reading, measurements, and image exports, took 19.2
seconds for both files. Boundary agreement improved over Tiny without changing
counts. This is a useful candidate for the accuracy preset; it is not an
independent accuracy evaluation.

Tiny was also tested with 64 × 64 sampling on the GPU. Counts remained 67/74 and
42/45, so higher prompt density was not adopted as the default. That run took
39.1 seconds for both files. The two unmatched MATLAB objects are partial border
nuclei (centroid X approximately 17 and 1363 in a 1392-pixel-wide field); denser
sampling did not recover them. Border inclusion needs an explicit review rule.

The denser run exposed upstream retention of unused per-candidate 256 × 256
mask logits. The adapter now releases these immediately after each batch's
refinement, before combining candidates, avoiding memory growth with prompt
count. Repeating the Small run kept all counts and one-to-one matches unchanged;
the original/compact runs had mean matched IoU above 0.9996. GPU runs were not
bitwise identical at mask boundaries (228 and 208 foreground pixels differed),
so exact-pixel equality is not claimed for model inference. Cache masks for
repeatable threshold comparisons. The completed 64 × 64 Tiny run peaked at 0.81
GiB of PyTorch-allocated GPU memory; that excludes other applications, the CUDA
context, and allocator-reserved memory. Inference never requires an OpenCV or
custom CUDA-extension dependency.

## Reproduction

```powershell
# Optional one-time independent MATLAB re-export:
matlab -batch "run('tools/export_matlab_reference.m')"

# Replays historical masks; exports reference results and detailed errors:
python tools/validate_baseline.py

# Generate updated predictions:
python -m nucleus_analysis pnc_counting/testfiles/testfiles --backend sam2 --checkpoint models/sam2.1_hiera_tiny.pt --output results/tiny --cache results/cache

# Substitute the per-image output directory printed/saved by the CLI:
python tools/compare_segmentations.py validation/local/baseline/IMG1/images.npz results/tiny/IMG1-PATH_HASH/images.npz
```

The comparison tool also accepts an integer-labelled reviewed TIFF as reference
(zero background, one ID per nucleus). Candidate `.mat` masks remain importable;
new caches contain sparse candidate indices in NPZ with no pickle.

## Before claiming equal or higher biological accuracy

1. Review a representative set of fields across HeLa/PC3M, low/high/small PNC
   signals, touching nuclei, partial border cells, and different acquisition
   settings. Produce manual nucleus labels and reviewed PNC-positive calls.
2. Define inclusion of border/mitotic nuclei, the target phenotype, and whether
   positivity is based on positive pixel area or distinct PNC puncta. The current
   rule counts positive pixels, as the MATLAB app did.
3. Keep a held-out set. Tune model size, sampling density, area, and PNC
   thresholds on a separate set; avoid tuning to these two example counts.
4. Compare one-to-one instance precision/recall/F1, matched IoU, nucleus and PNC+
   count errors, and percentage error on the held-out set. Inspect overlays for
   merge/split failures. Measure speed, memory, and checkpoint size alongside
   accuracy on the intended distribution hardware.

Automated tests cover synthetic touching nuclei, positivity boundaries,
overlap suppression, blank fields, axis selection, ambiguous axes, settings,
legacy mask conversion, SVM scores, TIFF/CLI/export behavior, and local real-data
count regressions. CI runs the portable tests without MATLAB, model downloads,
or private images; this does not certify all model/hardware combinations.
