# PNC Counter v0.7 progress

Updated 28 November 2026. This tracker records completed research, unresolved
findings and the next approved work. **A completed experiment does not mean that
its detector is ready for adoption.**

Stable download: **v0.6.0**. Latest local installer: **0.7.0.dev2**.
Latest measured research source: **0.7.0.dev4**, commit
`009f985be87061b7ce045f92adc438e0bde3744b` (5B; documentation-only
changes since step 4, with unchanged application algorithms). Both sides of the
guard comparison use app version **0.7.0.dev4**; rendering revisions are separate.
No improved biological accuracy has been demonstrated. Final v0.7 publication
requires the owner's local testing and explicit approval.

## Progress table

| Work | Status | Result | What remains |
| --- | --- | --- | --- |
| Stable Python app and Windows release | Done | v0.6.0 remains the public download. | Preserve stable behavior while research continues. |
| Preview workflow, consistent projections, live slider and saved revisions | Done | dev2 installer passed installation, ND2 export and review checks; 152 tests passed. | Owner testing; these checks establish functionality, not biological accuracy. |
| Training-free detector comparison and loss audit | Done; proposed replacements rejected | dev4 research passed 163 tests and Ruff. Tested enrichment/mixture operating points did not satisfy the separation/preservation proxy. | Retain legacy defaults. See the [versioned comparison](v070-enrichment-exploration.md). |
| Development/validation split | Done; exploratory | Seed 20261128: 22 development fields and 15 validation fields, approximately 60/40. | Previously examined data and unknown specimen relationships limit independence. Do not retune on validation. |
| Background step 1: controlled synthetic diagnostic | Done | Raw-intensity percentile trimming biased background estimation on a smooth gradient. | Determine which mechanisms affect real nuclei. |
| Background step 2: three real nuclei | Done | Dev2/dev4 maps and profiles exposed spatial reference selection and bright-focus contamination. | True background and candidate identity remain unreviewed. |
| Step 2 intensity histograms | Done | Report revision 3 includes linear/log counts, reference subsets and prior candidate footprints. | Histograms require spatial context; a separate bright peak is not required or established. |
| Step 3: retain low tail in background weights | Done; mixed result | Synthetic gradient error decreased, but flat-background error worsened and upper-tail bias remained. | Do not adopt this as a general correction. |
| Step 3: filtering plus p99 candidates | Done; no added accepted-region benefit in this test | Excess checks rejected the two no-spot scenes; p99 changed no accepted regions. Gradient misses, hot pixels and boundary artifacts remained. | Investigate local background/noise rather than rescue thresholds. |
| Step 4: local plane background and local noise | Done; useful controlled result | Local background recovered the strong gradient spot; local noise additionally recovered the faint spot. All five supported original no-spot probes stayed negative. | Real-reference contamination, curved-background adequacy and the small real example remain unresolved. This was probe evidence, not a full-field detector. |
| Step 4: raw spatial support | Done as diagnostic | The hot pixel had one raw support pixel despite 17 filtered support pixels. | No rejection rule adopted; a rule could also reject small signals. |
| Independent Big-FISH baseline | Blocked; not run | Separate research installation could not obtain the pinned NumPy distribution. Product dependencies unchanged. | Optional baseline when a compatible research environment is available; do not block the next diagnostic on it. |
| Step 5A: inspect the real small example | Done; inspection only | SAG5A-dev4-r1-20261128: filtered excess 37.05/40.02 is below the unchanged seed cutoff 80.68; no size/hot-pixel veto caused the probe's failure to pass. | The target was unconfirmed; the owner subsequently did not accept this location (A) as convincing PNC at displayed brightness. This is not a known-positive miss. Raw reference MAD 45.68 is not verified instrument noise. |
| Step 5B: one expanded-guard comparison | Done; useful mixed result | SAG5B-dev4-r1-20261128: reference guard 8 to 12 sigma only; positive anchor prior-footprint fit weight 15.70% to 2.63%. All 29 probe component outcomes unchanged; five original supported no-spot probes remain empty. | Nearby-focus contamination persists; curved central-background RMSE worsens 6.453 to 7.772; unconfirmed small anchor stays below cutoff, hot pixel still passes. Three boundary probes remain indeterminate. No second guard tried. |
| Owner biological review of small IMG9/n23 locations A/B/C | Done; provisional qualitative review | At raw display 688–1668 without smoothing, none was accepted as convincing PNC; the owner requires substantially brighter enrichment. | This is not an exhaustive negative annotation of the nucleus/image/folder, and supplies no numerical brightness threshold. Preserve historical measurements; do not rescue these locations by threshold changes. |
| Owner-confirmed clearly positive target | Pending bridge clarification | No A/B/C location is established as a known-positive preservation target. | Obtain a clearly positive example and intended location through the bridge, then quantify contextual enrichment/background and evaluate frozen methods there. No new experiment launched. |
| Biological identification and detector adoption | Pending | Steps 4 and 5 provide controlled diagnostic progress; no product detector adopted. | A clearly positive target is needed; structured-reference variation and plane adequacy remain unresolved. No biological improvement claim. |
| Automatic full-field integration and wider validation | Deferred | Current work remains diagnostic research. | Review step 5 before expanding candidate generation, adding rejection rules or measuring validation again. |
| Final v0.7 release | Pending owner approval | No release, tag or promotion authorized. | Demonstrate useful real-image behavior and complete owner testing. |

## Checkpoint 5: completed; review pending

The v0.7 agent owns execution and report updates; the bridge agent maintains the
handoff and release boundary. The owner approved this next step on 28 November.
Execution status: **5A and 5B are complete; product adoption is pending.** The
paragraphs below retain the approved scope and do not authorize further work.

**5A: inspect the small example before changing a rule.** Reuse the fixed small
IMG9/nucleus 23 selection. Show the whole nucleus and a native-resolution pixel
crop so the reviewer can locate the prior two-pixel footprint among surrounding
structures. Include pixel values, fixed line profiles, background prediction,
local-reference pixels, raw/filtered residuals and intensity histograms. Separate
background subtraction, local noise width and threshold contributions. Treat the
local width as reference variation until its noise interpretation is supported.
No new threshold or hot-pixel veto belongs in this phase.

**5B: test one guard expansion separately.** Predeclare one expanded inner guard
from physical scale/geometry, keeping the step-4 outer reference radius, plane
model, robust-fitting settings, SAM masks, filter, decision constants and probe
locations fixed. Re-estimate the same quantities under that single geometry
change and report any resulting noise-width changes as outcomes. Compare both
guards on the same three development nuclei and preserved synthetic scenes,
including curved, neighboring-focus and boundary cases. Quantify prior-footprint
overlap and reference weight, fitted background, adequacy diagnostics and support
loss. A better-conditioned fit or a larger residual alone is not success.

Preserve insufficient/one-sided fits as **indeterminate**, rather than silently
negative. Check model inadequacy as well as numerical conditioning. If the larger
guard still contains structure or removes necessary reference support, report the
failure without trying successive guard sizes.

Return a review checkpoint before further methods, parameter searches, broader
candidate generation or product integration. All processing remains local and
self-contained within each image/nucleus, without external control calibration,
exposure scaling or model training.

## Report requirements

For each checkpoint, update the relevant rows above and append the experiment ID,
exact version, source commit/hash, report link and concise outcome below. Keep
completed reports immutable and identify the current rendering revision. A pure
diagnostic/rendering revision does not imply a new application version.

Report the same inputs and denominators before and after, changed versus fixed
settings, known synthetic background/signal errors, real descriptive changes,
failures, support/adequacy flags and runtime scope. Separate automatic calls from
manual overrides. Folder labels and unreviewed footprints are not biological
truth. Preserve previous installer, export and source hashes. Use a next unused
development version only if tracked implementation changes warrant it.

## Local evidence index

These reports contain private microscopy data and remain in ignored local
storage. The links resolve in the working checkout; they are not public release
assets or files included in the Git repository.

| Checkpoint | Version or experiment | Local report |
| --- | --- | --- |
| Paired 60/40 comparison | dev2 before / dev4 research after | [Comparison](../validation/local/pnc-discrimination/v070-dev4/exploration-60-40/report.html) |
| Background step 1 | dev4 synthetic diagnostic | [Step 1](../validation/local/pnc-discrimination/background-audit-step1-dev4/report.html) |
| Background step 2 with histograms | dev4, report revision 3 | [Step 2](../validation/local/pnc-discrimination/background-audit-step2-dev4/report-v3.html) |
| Background and histogram step 3 | BGH3 dev4 revision 1 | [Step 3](../validation/local/pnc-discrimination/background-histogram-step3-dev4/report.html) |
| Local background and noise step 4 | LPN4-dev4-r1-20261128 | [Step 4](../validation/local/pnc-discrimination/local-plane-noise-step4-dev4/report.html) |
| Small example step 5A | SAG5A-dev4-r1-20261128; app dev4, render 1; clean measurement HEAD c9e57c9243b82e5922427deae3b5663f0121f18e | [Native small-anchor inspection](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/report-a.html) |
| Guard comparison step 5B | SAG5B-dev4-r1-20261128; app dev4 before/after, render 2; clean measurement HEAD 009f985be87061b7ce045f92adc438e0bde3744b | [One-guard comparison](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/report-b-v2.html) |
| Owner biological review of A/B/C | Qualitative review revision 2; source dev4 unchanged; informational steering after step 5 | [Reviewed raw image](../validation/local/pnc-discrimination/small-anchor-owner-review/small-example-ABC.png), [verbatim feedback and provenance](../validation/local/pnc-discrimination/small-anchor-owner-review/owner-review-v2.json) |

### Owner biological review: small IMG9/n23

The owner reviewed the saved whole nucleus and nearest-pixel raw zooms of three
locations: **A central (74,76), B upper-left (50,59), C lower-left (51,78)**,
in zero-based crop **X/Y** coordinates. The display used linear raw limits
**688–1668**, the saved maximum-Z projection and no smoothing. A is the previously
selected central two-pixel probe. The owner first said, "i dont think that is the
true PNC." After reviewing A/B/C, the owner said, "i wouldnt consider those PNCs
unless they are significantly brighter".

Record **all three as not accepted as convincing PNC at the displayed
brightness**, a provisional qualitative review. This does not establish an
exhaustive negative label for the nucleus, image or PNC-small folder. A/B/C must
not be treated as known-positive misses or targets for threshold rescue.
Small-folder membership and preserved legacy calls cannot establish true-positive
preservation. Substantial brightness enrichment within the image/nucleus context
is part of the owner's biological appearance requirement; a statistically
detectable local peak alone is insufficient. No absolute or fold-change threshold
can be inferred from this comment.

Earlier "small miss" wording refers to a selected, **unconfirmed probe failing
the frozen numerical rule**, not a demonstrated failure to detect a true PNC.
All historical counts, arrays and reports remain unchanged. The review changes
their biological interpretation, not the measured outputs. No product/manual
calls, labels used for validation, thresholds or fitting rules were changed.

The next scientific need is an **owner-confirmed clearly positive example and
intended target**, to be clarified through the bridge. Then relative enrichment
and background can be quantified in per-image/per-nucleus context and frozen
methods assessed at that intended positive target. This update authorizes no
additional guard/threshold fitting, parameter sweep or biological accuracy claim;
no new experiment was run.

Private evidence: [review revision 2](../validation/local/pnc-discrimination/small-anchor-owner-review/owner-review-v2.json)
retains the verbatim history, coordinates and source hashes;
[the original review](../validation/local/pnc-discrimination/small-anchor-owner-review/owner-review.json)
is unchanged and [the rendering script](../validation/local/pnc-discrimination/small-anchor-owner-review/plot_review.py)
reproduces [the reviewed image](../validation/local/pnc-discrimination/small-anchor-owner-review/small-example-ABC.png).
Verified SHA256 values: review revision 2
`9eae47d8506d7ca9b91e73a7c1e380e115d739738c25c4cf708b37c437e4b098`;
reviewed figure
`66c5bf093d6dbd68981bc63eb78a02e6382a6e1581965386e3ff041c32b5fda4`;
preserved original review
`2c06e6aa30034282938be0c418bd17dc907ea544b47cfee9b8749536e11b93f0`.
Figure, parent-review and saved-input hashes match the revision-2 provenance.

### Checkpoint 5 before/after findings

The same three DEVELOPMENT nuclei and ten preserved synthetic inputs (the
original nine scenes plus the step-4 curved stress case) supplied 29 fixed
probes. Evaluation cores, SAM geometry, filter, plane/Huber settings, noise-width
formula, decision constants and support checks stayed fixed. Only the reference
inner guard changed from 8 to 12 sigma, with the outer radius at 20 sigma. The
report separates the background change with old width frozen from recomputing
the same width formula on the changed reference. Neither condition is a product
detector or a biological call. No validation data were remeasured.

| Fixed measure | Before: dev4, guard 8 | After: dev4, guard 12 |
| --- | --- | --- |
| Positive real anchor prior-footprint reference overlap / fit weight | 203 pixels / 15.70% | 35 pixels / 2.63%; contamination not eliminated |
| Positive real nearby probe footprint overlap / fit weight | 197 / 12.58% | 150 / 12.02%; off-center contamination remains |
| Unconfirmed small-folder anchor filtered excess / seed cutoff | 40.02 / 80.68 | 33.73 / 77.16; below cutoff (80.68 with old width frozen); not a known-positive miss |
| Strong gradient injected signal retained in identical core | 99.97346% | 99.99999%; original region remains |
| Irregular injected signal retained in identical core | 99.64641% | 99.99952%; original region remains |
| Curved no-spot central core background RMSE | 6.45288 | 7.77172; worsens despite lower reference MAD and better conditioning |
| Nearby strong-focus synthetic core background RMSE | 0.31521 | 0.39163; worsens |
| Supported no-spot probes with any accepted region | 0/5 original; 0/2 curved stress | 0/5 original; 0/2 curved stress |
| Hot-pixel filtered support / boundary probes | 17 pixels; three indeterminate | 17 pixels; three indeterminate |

All 26 supported probe component counts are unchanged; the same three boundary
probes remain indeterminate. Some support pixels change, including the positive
nearby probe (4 to 6). Small-reference raw MAD changes 45.68 to 43.36, but neither
value is verified instrument noise. The negative-folder anchor still has strong
localized evidence; folder membership cannot establish a false PNC call.

Use the [whole-nucleus location](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/small-context.png),
[native 21-by-21 crop](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/small-anchor-native.png)
and [actual-pixel grid](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/small-pixel-grid.png)
to review the unconfirmed two-pixel structure. Guard-comparison
[small profiles/histograms](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/guard-plots-r2/PNC-small-IMG9-n23-anchor-profiles-histograms.png),
[positive reference profiles](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/guard-plots-r2/PNC-positive-IMG1-n74-anchor-profiles-histograms.png)
and [curved-background maps](../validation/local/pnc-discrimination/small-anchor-guard-step5-dev4/guard-plots-r2/curved-no-spot-stress-anchor-maps.png)
show the mixed result. The full report includes every probe, matched scales,
fixed profiles, exact arrays and population-counted histograms. Rendering 1 is
preserved; rendering 2 clarifies display labels/domains without new measurements.

Targeted checks: all 29 baseline fits reproduce step 4; common cores/windows and
reference-subset checks pass; native raw TIFF is exact; histogram counts and
local links pass. All 251 protected files are hash-unchanged, including prior
reports/arrays and the dev2 installer. The 61 original 5B rendering files also
remain unchanged. Fit-only median timings were 3.019 ms before and 2.341 ms after
on 29 probes in an existing CPU Python process; these exclude imports/loading,
evidence, rendering, cold app/SAM preparation and warm-slider latency. No product
suite was rerun because implementation did not change.

**Current review recommendation:** do not adopt guard growth as a general
correction or seek to rescue the reviewed A/B/C locations. Following the owner's
qualitative review, first obtain a clearly positive example and intended location
through the bridge, then quantify relative enrichment/background and assess
frozen methods at that target. Plane adequacy and structured-reference variation
remain open issues. Stop here pending positive-example clarification; no further
experiment, threshold rescue, hot-pixel rule or dependency retry was performed.

Step 5 algorithm provenance: application enrichment SHA256
`2ff62e9a89f85f01748d8ed87b0f4556f0413624f7bf3138191c253e82af8b90`;
preserved LPN4 diagnostic SHA256
`29047cd45e9e5b708aa5ae3d03aada97b52d60c8daf6ed740489b4ced3595636`.
The original LPN4 clean source commit is
`5df32d0fcb2f012bf870e33c145cd1119e3cfccf`. 5A inspection-script SHA256 is
`9228a580a84ee8480fbcf9e235816b1d60167976dc19d04e83a5c3b3420f947d`;
5B experiment-script SHA256 is
`798f9a02721bead70e3e21d949a8ddd987eae33afd1a410369222181a107ed84`.
The diagnostic fit-function hashes are
`6752f618b2b4e11de9981c428e8ae077eff028384adcaa9d4352f35bcdd159dc`
before and `e99d3db9406e233ccc1ec2f04651c2f6db3961bca86ac4fd16f00b6a3fa14e4c`
after; their ASTs differ only by the reference-selection constant 8 to 12.
Exact input, unchanged evidence-function, rendering and protected-artifact hashes
remain in the local plans/results and verification files. No estimator or
decision rule was rerun in 5A. Final documentation/delivery commit and clean state
are recorded separately in the local handoff, rather than replacing measured HEADs.
