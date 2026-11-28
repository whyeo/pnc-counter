# PNC Counter v0.7 progress

Updated 28 November 2026. This tracker records completed research, unresolved
findings and the next approved work. **A completed experiment does not mean that
its detector is ready for adoption.**

Stable download: **v0.6.0**. Latest local installer: **0.7.0.dev6**;
the earlier dev2 installer and its original metadata are preserved.
Previous measured research source: **0.7.0.dev4**, commit
`9f565cf57857f146742f2dd3bc7335a1ddff1854` (step 7; documentation-only
changes since step 4, with unchanged application algorithms). All frozen-method
comparisons use app version **0.7.0.dev4**; rendering revisions are separate.
No improved biological accuracy has been demonstrated. Final v0.7 publication
requires the owner's local testing and explicit approval.

## Current local implementation

**0.7.0.dev6 retains the owner-approved 1.8x local enrichment default and implements
the selected fixed side-panel layout in native Python/Tk.** The threshold is
above the image, manual calls/exclusion/navigation and Save stay visible, and
less-used controls move into More actions / Advanced. Numeric entry shows two
decimals. Spatial display numbers map to persistent mask IDs in every export.
Earlier analyses retain their
stored protocols until explicitly switched. The owner approved the native layout
and authorized packaging. Owner acceptance of the packaged build remains
pending; no stable v0.7 tag or publication is approved.

Dev6 checks: **179 tests passed**, Ruff and whitespace checks passed. The native
950x650 layout test keeps threshold entry, manual calls, exclusion, navigation,
More actions and Save visible. Spatial order, stable-ID mapping, geometry edits,
undo and immutable save/reopen are covered. A real 1040x1392 saved-field smoke
test passed at 1.2x / 1.8x / 2.5x with unchanged 69 / 65 / 58 positive calls out
of 74, fixed masks and no SAM invocation. Saving/reopening also passed. Four
warm updates had median 0.589s and p95 0.602s including debounce/rendering;
this is a local check, not a speed improvement claim.
See the [native dev6 window](../validation/local/pnc-discrimination/v070-dev6/native-side-panel.png)
and [saved-field check](../validation/local/pnc-discrimination/v070-dev6/slider/slider-verification.json).

Dev6 owner-feedback follow-up: initial review opening now automatically fits the
image; subsequent window remapping preserves user zoom. Sensitivity captions
anchor independently to the slider endpoints, and main-window buttons use larger
padding/type. **51 targeted desktop/review tests passed**, including auto-fit,
caption alignment and main-button visibility at 920x650; Ruff and whitespace
checks passed. This follow-up changes UI behavior, not detector scoring.
The saved-field opening check also fits the image without calling Fit manually;
counts remain 65/74 at 1.8x. See the
[updated review window](../validation/local/pnc-discrimination/v070-dev6/layout-followup/review-window.png)
and [larger main-window buttons](../validation/local/pnc-discrimination/v070-dev6/layout-followup/main-window.png).

The bridge completed implementation locally after the v0.7 session handoff did
not acknowledge delivery. The latest usage guide is [README.md](../README.md);
version history is in [CHANGELOG.md](../CHANGELOG.md).

Previous dev5 engineering checks: **175 tests passed**, Ruff passed, and all **1,391** retained
nucleus enrichment maxima across **37** saved fields reproduced the explorer.
At 1.8x, calls are negative-folder 59/299, positive-folder 666/810 and small-folder
13/282. These are exploratory call rates, not measured classification accuracy.
The native slider/save/reopen check passed without SAM; four warm updates on a
1040x1392 field had median 0.562s including debounce and rendering. See the
[local desktop screenshot](../validation/local/pnc-discrimination/v070-dev5/desktop-enrichment-ui.png).
The dev6 Windows preview is now packaged from clean source
`0510328f5ce8df2f1a1f2267556ea82bfb09717f`:
[PNC-Counter-0.7.0.dev6-Preview-Setup-x64.exe](../dist/preview/0.7.0.dev6/PNC-Counter-0.7.0.dev6-Preview-Setup-x64.exe).
Size: 69,879,076 bytes. SHA-256:
`ae2927b845611844ce0b4fb6fc73d8976e2b969f5e75d9bd5595a695dd298b24`.
The updated README, changelog and install/review guides are bundled.
All 180 source tests and Ruff pass. Actual isolated installation, public ND2
analysis/export (watershed functional backend), installed enrichment slider,
immutable save/reopen and uninstall pass. Review calls at 1.2x/1.8x/2.5x remain
69/65/58 out of 74 with fixed masks and no SAM rerun. All 34 application Python
files match the wheel, and five earlier preview assets are hash-unchanged.
See the [packaged verification summary](../dist/preview/0.7.0.dev6/verification.json).
This was the existing Windows development machine; a separate clean-machine
test and a fresh SAM-engine setup were not repeated for this build. No release
has been pushed, tagged or published.

## Progress table

| Work | Status | Result | What remains |
| --- | --- | --- | --- |
| Current Windows preview package | Done locally; owner packaged testing pending | dev6 setup, checksum/provenance and current docs available. Installation, ND2 export, installed slider/save/reopen and uninstall pass. | Owner testing of the installer; separate clean-machine/fresh engine check before stable release. |
| Native side-panel redesign and spatial numbering | Owner layout review approved; packaged testing pending | Owner selected Side panel mockup and approved native UI follow-ups. Fixed controls, spatial numbers, auto-fit and larger buttons are in dev6. | Owner testing of the packaged build; final release approval remains pending. |
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
| Owner-confirmed clearly positive target | Done; indicated location confirmed | Owner answered "yes P is" for P, positive IMG1/n74, crop X69/Y75. P is the original fixed LPN4/SAG5 positive anchor. | Confirmation covers the indicated location, not an exact boundary, other candidates or the folder. A/B/C remain provisionally nonconvincing. |
| Step 6: frozen-method comparison of reviewed P/A/B/C | Done; diagnostic only | RPC6-dev4-r1-20261128: P passes every frozen stage; A passes none. Whole-nucleus-width stages reject B/C; existing local-width stages accept B/C despite their nonconvincing review. P/A saved outcomes reused; only four B/C fits and ten evidence calls added. | Statistical detectability alone does not establish PNC identity. Review the separation/tradeoff before broader work; no threshold fitted or product detector adopted. |
| Interactive development review panel | Owner review complete; UI ready | PNC-DEV-REVIEW-01, rendering 3: 12/12 reviewed, 5 Positive / 7 Negative / 0 Unsure; bridge build/QA and owner review are distinct completed steps. | Preserve the immutable completed snapshot; a stale browser tab may still show zero. |
| Owner review of the 12 additional targets | Complete; 12/12 | Immutable owner snapshot: 5 Positive (R01/R02/R03/R06/R10), 7 Negative (R04/R05/R07/R08/R09/R11/R12), 0 Unsure/missing, no notes. Labels cover indicated targets only. | Preserve the exact snapshot/hash; do not use a stale browser tab, latest pointer, zero-label smoke snapshot or isolated QA data as evidence. |
| Descriptive contrast comparison of the additional panel | Done; exploratory descriptive result | DRC7-dev4-r1-20261128: median-ratio ranges 1.74094–4.81554x for 5 positives and 1.05186–1.18622x for 7 negatives; no observed range overlap. P/A/B/C kept separate. | R10 has one-sided reference support; all rings intersect permissive stored growth supports. Existing LocalContrast also separates these points; no validated cutoff or demonstrated detector improvement. |
| Local enrichment default | Approved and implemented locally | dev5 new settings use the raw3x3/ring descriptor at 1.8x. Historical saved protocols remain reproducible. | Owner UI testing; broader biological accuracy remains unmeasured. |
| Full-field app integration | Done locally | 1,391 nucleus maxima and automatic calls reproduce NE8 at 1.8x; CLI, review revisions and exports include the new protocol. | Human review and local acceptance; all previously examined fields remain exploratory. |
| Native threshold interface | Ready for owner testing | Direct fold slider, numeric entry, reset1.8x, live counts/overlays and Use for next analysis. Source UI open locally. | Owner feedback before packaging/finalization. |
| Latest-revision README and changelog | Done | README describes dev6 usage only; history remains in separate CHANGELOG.md. | Keep documentation aligned with later changes. |
| Final v0.7 release | Pending owner approval | No release, tag or promotion authorized. | Demonstrate useful real-image behavior and complete owner testing. |

## Interactive owner review and descriptive comparison: complete

The bridge built and opened **PNC-DEV-REVIEW-01**, rendering **3**, at the
[local review page](http://127.0.0.1:8776/review.html). This is a loopback-only
review tool with self-contained raw 16-bit crops; it does not change the product
detector. Panel build provenance is app **0.7.0.dev4**, clean source commit
`693ce1c1a92a1e693f781bcd99e9619fde5a71ef`. The latest measured research HEAD
above records the completed descriptive checkpoint; building a review interface
added no detector measurement. The owner's subsequent completed snapshot supplies
the target-level labels below.

**Owner review is COMPLETE: 12/12, 5 Positive / 7 Negative / 0 Unsure.** There are
no missing choices or notes. The owner used another tab/browser, so an original
integrated tab may still show zero; do not save that stale view over the completed
review. Use only the bridge-provided [immutable owner snapshot](../validation/local/pnc-discrimination/interactive-owner-review/reviews/review-20261128T064807-f9ee3275.json),
SHA256 `392f91971672030d3198df2d57adc9dd2b4752a9534e3ad90f7ace91d7e72a57`.
It has `testMode=false`, matching panel ID/image hashes, and the bridge's
[completed-review verification](../validation/local/pnc-discrimination/interactive-owner-review/completed-review-verification.json).
The initial empty save was only a save-path check; neither it nor isolated QA data
is owner evidence. This bookkeeping/analysis reads the fixed saved snapshot,
without browser interaction or response changes.

The panel uses stored **A-growth** measured candidates, taking the strongest
stored LocalContrast per eligible accepted/unoverridden nucleus, with candidate
area at least 3 pixels and seed inside the saved SAM mask. The three previously
inspected nuclei are excluded. Selection contains one target per development
field, four per folder and four per sampling stratum, randomized with seed
**20261128**. Weak/intermediate/strong sampling uses **within-folder contrast
thirds**, providing variety within each folder rather than globally matched
cutoffs. The initial global-thirds quota was unavailable; that failed plan was
preserved and the amendment preceded rendering and owner review. No owner labels
or desired biological outcomes were used in selection. Folder, stratum and scores
are hidden from the reviewer; folder membership is not biological truth.

This is a selected, exploratory development panel, not prevalence estimation or
independent accuracy validation. Existing candidate extraction can omit other
true PNCs; the panel does not exhaustively label whole nuclei, fields or folders.
It introduces no new detector/PNC fit, raw ND2 reading, validation access,
training, threshold or model selection. The authorized descriptive comparison is
now **COMPLETE**, using a plan frozen before calculation and the completed
immutable labels. It retained the same fixed targets/denominators and existing
raw3x3 median/peak divided by eroded in-nucleus annulus12–20 saved small-sigma
median convention. Reference samples and support/contamination/mapping checks
are preserved; previous P/A/B/C results remain separate. No optimized cutoff,
new threshold/model, broader run or algorithm adoption was performed.

The bridge's [UI verification](../validation/local/pnc-discrimination/interactive-owner-review/ui-verification.json)
records isolated test storage for buttons/keyboard, notes/navigation, reload,
export/import and rejection, completion, mobile display and local API checks;
test choices were removed and no fabricated labels were saved to real reviews.
Direct Save review was verified. Native browser-download events were unavailable
in the integrated browser, so direct local saving is the verified path. No UI/API
tests were rerun for this documentation-only update.

Private setup/provenance: [selection plan](../validation/local/pnc-discrimination/interactive-owner-review/plan.json),
[build verification](../validation/local/pnc-discrimination/interactive-owner-review/build-verification.json),
[review instructions](../validation/local/pnc-discrimination/interactive-owner-review/README.txt)
and [self-contained HTML](../validation/local/pnc-discrimination/interactive-owner-review/review.html).
The private manifest retains the R01–R12 mapping and exact source image, mask,
candidate and feature hashes. Verified SHA256 values: panel HTML
`da579313780498856e2f4db41123bfd28d174f16d81357ba92dabf9196d9216d`;
selection manifest
`374e6fa372ef843e10f805125da0d22e211777f7855d851a90947258d440cb84`.
These match the bridge's build/UI verification records. Application source,
prior artifacts, stable **v0.6.0** and installable **dev2** remain unchanged;
no publication, push, tag, merge, package, release or deployment is authorized.

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
| Owner confirmation of P | Confirmation revision 2; source dev4 unchanged | [Confirmed review report](../validation/local/pnc-discrimination/positive-reference-owner-review/report-v2.html), [verbatim confirmation and provenance](../validation/local/pnc-discrimination/positive-reference-owner-review/owner-confirmation-v2.json) |
| Reviewed points step 6 | RPC6-dev4-r1-20261128; app dev4 before/after, render 1; clean measurement HEAD 6adb2e6a14de7b89923345e69bc79f9018fb2af4 | [Frozen P/A/B/C comparison](../validation/local/pnc-discrimination/reviewed-points-step6-dev4/report.html) |
| Interactive additional development panel | PNC-DEV-REVIEW-01; app dev4, rendering 3; built at clean HEAD 693ce1c1a92a1e693f781bcd99e9619fde5a71ef; owner review complete 5 Positive / 7 Negative | [Immutable owner snapshot](../validation/local/pnc-discrimination/interactive-owner-review/reviews/review-20261128T064807-f9ee3275.json), [completion verification](../validation/local/pnc-discrimination/interactive-owner-review/completed-review-verification.json), [build record](../validation/local/pnc-discrimination/interactive-owner-review/build-verification.json) |
| Descriptive reviewed-panel contrast | DRC7-dev4-r1-20261128; app dev4 before/after, rendering 1; clean measurement HEAD 9f565cf57857f146742f2dd3bc7335a1ddff1854 | [Completed 12-target contrast report](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/report.html) |

### Step 7: completed owner-panel contrast checkpoint

**DRC7-dev4-r1-20261128 is complete; product adoption remains pending.** App
BEFORE **0.7.0.dev4** / AFTER **0.7.0.dev4**; no implementation changed. This
adds descriptive measurements to the completed owner panel, not a paired rerun
of a detector or a claim of improvement against an invented prior 12-point
baseline. The frozen plan identifies the exact immutable review/manifest hashes,
configuration and source exports. Only saved development data were read; no raw
ND2, detector/background/noise fit, validation measurement or browser response
update was needed.

The pre-existing convention uses the unsmoothed raw 3-by-3 median/peak at each
fixed reviewed seed, divided by the raw median of its one-pixel-eroded SAM
annulus at 12–20 saved small-sigma units. For all 12, calibration is
0.107495210727969 micrometres/pixel and sigma is 0.9302740031 pixels; ring radii
are 1.2–2.0 micrometres. No recentering, smoothing, reference trimming, exposure
normalization, external controls or new parameter choice was introduced.

| Owner target label | n | Raw3x3 median / ring median: range | Group median | Raw3x3 peak / ring median: range |
| --- | --- | --- | --- | --- |
| Positive | 5 | 1.74094–4.81554x | 3.48018x | 1.90036–5.09804x |
| Negative | 7 | 1.05186–1.18622x | 1.09864x | 1.08259–1.25359x |

Neither predeclared ratio has observed positive/negative range overlap in these
12 selected targets. The gap between median-ratio extrema 1.18622 and 1.74094 is
descriptive only; no cutoff inside it was chosen, tested or called validated.
This makes simple local enrichment useful evidence here, not a classifier,
independent validation, accuracy estimate or general biological threshold.
Existing stored footprint LocalContrast also separates these reviewed ranges,
so superiority over that measure has not been demonstrated. Stored integrated
SignalScore overlaps (positive R02 2.91682; negative R05 3.01140); those unchanged
scores and raw-support/noise estimates are separate from the new ratios.

Important limitations and counterexamples remain in the full report:

- **R02 is owner-positive despite the PNC-negative folder**, with median
  enrichment 1.74094x. Folder labels are not per-target truth. Its ring includes
  421 pixels of other stored growth support and two other measured seeds.
- **R10 is owner-positive at 1.93206x**, with 539 ring pixels and angular counts
  `[89,88,89,88,89,37,2,57]`; it fails the existing diagnostic minimum of 4 per
  sector. Retain its value with a one-sided-reference warning, not a fallback,
  exclusion or negative biological call. The other 11 rings have 708 pixels.
- **All 12 rings intersect stored A-growth supports.** At negative R07, 706/708
  reference pixels carry a stored growth label. These permissive supports are
  not owner-annotated PNC masks: overlap flags possible reference contamination,
  not proven biological objects. No ring is established as clean nucleoplasm.
- Raw intensities differ across acquisitions, and reference MAD/IQR contains
  structure/gradients as well as unknown noise. Neither it nor stored Noise is
  calibrated instrument noise. P/A/B/C values are shown only as a separate prior
  reference; they were not pooled with the new 5/7 distributions.

Every target's raw and relative-intensity maps, fixed profiles, actual reference
histograms/pixels, stored support overlays, original candidate measurements and
acquisition metadata are retained. See the [full private report](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/report.html),
[all-12 distribution figure](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/plots/all12-distributions.png),
[R10 boundary/reference example](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/plots/R10-raw-relative-reference.png)
and [per-target table](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/per-target.csv).

All 12 source export hashes, embedded review-page raw bytes/targets/masks,
whole-to-crop coordinates, physical scale, seed ownership, stored candidate
seed/area and eligibility/exclusion checks pass. No raw3x3 window leaves its
selected SAM mask, no reference pixel is owned by another nucleus, and no
target/reference sample reaches the recorded ADC ceiling. All **8,327 raw
reference samples** are preserved with coordinates in
[the reference CSV](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/reference-samples.csv)
and per-target arrays. Native uint16 TIFFs are exact; histogram counts and local
links pass. All **534 protected files** remain hash-unchanged, including the
immutable owner snapshot, earlier reports/sources/arrays and dev2 installer.
Runtime was 1.996 seconds for the 12 saved-export loads, mapping, descriptive
measurements and output writes; imports/hash preflight/rendering and any cold
app/SAM or warm-slider work are excluded. No product test suite was rerun for
unchanged implementation.

Measured clean HEAD: `9f565cf57857f146742f2dd3bc7335a1ddff1854`; unchanged
application source-tree Git hash: `8270e4af81e4955c21838f43c6bcecc451f37ebc`.
Ignored step-7 script SHA256:
`2d10300e97bfd8d63475f2412fa9c03eab800fa003bae56f951aa5bc5a340519`.
The [frozen analysis plan](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/plan.json)
and [preservation verification](../validation/local/pnc-discrimination/owner-panel-contrast-step7-dev4/verification.json)
record exact review, manifest, source/input and output hashes. Final tracker-only
documentation commit/delivery provenance is recorded separately in the handoff.

**Next review recommendation:** retain relative enrichment as auditable
descriptive evidence; review R02/R10 and reference-quality overlays before any
next bounded experiment or product change. This contrast-selected development
panel does not support an optimized cutoff or algorithm promotion. No further
work, training, broader validation or release is performed at this checkpoint.

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

This review initially left a clearly positive example unresolved. The subsequent
confirmation of P below fulfills that clarification; it does not reverse the
A/B/C review or justify a threshold rescue. No guard/threshold fitting, parameter
sweep or biological accuracy claim follows from either qualitative review.

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

### Owner-confirmed positive location P

The bridge displayed P in PNC positive/IMG1, nucleus 74, at zero-based crop
**X69/Y75**, using the saved whole raw maximum projection and a 31-pixel zoom.
Asked "Would you consider P a clear PNC-positive example?", the owner answered
**"yes P is"**. Record this indicated location as **OWNER-CONFIRMED PNC POSITIVE**.
There is no exact object-boundary annotation. P is the original positive anchor
already measured in LPN4/SAG5, not a new field selected for the desired outcome.
Neither this confirmation nor the A/B/C review extends to whole nuclei, images
or folders; the locations remain exploratory, not independent validation.

The bridge's existing descriptive comparison divides the raw 3-by-3 median by
the raw median of the eroded in-nucleus annulus at 12–20 saved small-sigma units,
with 708 reference pixels per location: **P 15159 / 3511.5 = 4.31696x**;
**A 1.01112x, B 1.15344x, C 1.12949x**. P's 3-by-3 peak ratio is **4.48298x**.
The ring can contain other structures; these are descriptive enrichment ratios,
not a calibrated SNR or proof of true background. They do not define a 4x rule,
general brightness cutoff or classifier. No external control/exposure adjustment
is used.

Current confirmation is in the [revision-2 record](../validation/local/pnc-discrimination/positive-reference-owner-review/owner-confirmation-v2.json)
and [confirmed report](../validation/local/pnc-discrimination/positive-reference-owner-review/report-v2.html).
The [P figure](../validation/local/pnc-discrimination/positive-reference-owner-review/positive-example-P.png)
and [P/A/B/C brightness figure](../validation/local/pnc-discrimination/positive-reference-owner-review/relative-brightness-PABC.png)
remain preserved. The older [descriptive review](../validation/local/pnc-discrimination/positive-reference-owner-review/review.json)
and original pending-review rendering retain their historical wording; the
revision-2 confirmation supplies the current biological status.

The completed bounded checkpoint compared only these four fixed locations
using existing frozen configurations: original LPN4 guard 8–20 sigma and the
already recorded SAG5 guard 12–20 comparator; the evaluation core remains
8 sigma. P/A fits and decisions were reused from saved results. Only B/C received
new fits and probe decisions with the identical existing functions/constants.
Candidate coordinates, indication-point overlap and raw support remain distinct
from a biological object mask. No new guard, model, threshold, training, broader
field run or validation measurement was performed. Confirmation revision-2 SHA256:
`a013ba9b808f233ebe3264eae857f58e126b20557ebc7b67300e0b6242a4ade2`;
the reviewed P-image SHA256 is
`a8032ec985b123bfb4c62ee1de89580be20d6091a52fc96fee909dd50d9568f5`.

### Step 6: reviewed points under frozen rules

**RPC6-dev4-r1-20261128 is complete; product adoption remains pending.** Before:
saved P/A numerical outcomes from LPN4/SAG5, app **0.7.0.dev4**. After: those
same outcomes interpreted with owner review, plus the first frozen B/C
measurements, still **0.7.0.dev4**. There are no historical B/C detector results
against which to claim a temporal improvement. Locations, labels and the two
existing reference geometries were fixed before the new measurements; no
configuration was selected from these outcomes.

| Point | Owner review | Descriptive median enrichment | B0 / whole width | Plane 8 / whole width | Plane 8 / local width | Plane 12 / frozen width 8 | Plane 12 / local width |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P, X69/Y75 | Confirmed PNC-positive location | 4.31696x | Pass | Pass | Pass | Pass | Pass |
| A, X74/Y76 | Provisionally nonconvincing at shown brightness | 1.01112x | No seed | No seed | No seed | No seed | No seed |
| B, X50/Y59 | Provisionally nonconvincing at shown brightness | 1.15344x | No seed | No seed | Pass | Pass | Pass |
| C, X51/Y78 | Provisionally nonconvincing at shown brightness | 1.12949x | No seed | No seed | Pass | Pass | Pass |

Pass means the existing numerical probe rule produced accepted support containing
the indicated pixel, not a new biological or manual app call. No seed identifies
the first rejection stage. All 20 stage outcomes, candidate coordinates/offsets,
reference/background values, fixed cutoffs and flags are in the private report.
The whole-width stages already separate these four reviewed locations; they are
probe adaptations of earlier G diagnostics, not complete product detector runs.
Prior faint-synthetic failures with whole-nucleus width remain relevant, so this
four-point result does not establish a generally preferable detector.

At the original plane-8 geometry, changing only the already defined width rule
from whole-nucleus to local reference variation yields:

| Point | Fitted background at point | Filtered excess | Whole / local width | Point score in whole / local width units | Local seed cutoff | Raw neighbors above 3x reference MAD |
| --- | --- | --- | --- | --- | --- | --- |
| P | 3867.04 | 11207.78 | 282.31 / 223.81 | 39.68 / 50.05 | 1125.09 | 8/8 |
| A | 1430.09 | 40.02 | 106.93 / 13.86 | 0.27 / 2.07 | 80.68 | 0/8 |
| B | 1326.59 | 233.57 | 106.93 / 15.13 | 2.08 / 14.69 | 87.02 | 8/8 |
| C | 1370.23 | 187.41 | 106.93 / 12.53 | 1.65 / 14.05 | 74.04 | 7/8 |

Scores are `(filtered excess - frozen original center) / width`, not calibrated
SNR, probability or biological confidence. B/C pass the unchanged 5-width seed
and 3-width localization tests despite only modest descriptive enrichment. They
also have spatially supported raw excess; raw-neighbor support alone does not
separate them from P. Under plane 8/local width, P/B/C have 177/89/74 filtered
support pixels, clipped to the fixed 177-pixel evaluation core. These are not true
object boundaries. B has two accepted seeds in one connected region, the closest
one pixel from its indicated location; C's seed is at its indicated point.

All four locations pass the existing reference-support/rank/conditioning checks;
none becomes indeterminate. The raw reference MADs for plane 8 are
737.79/45.68/49.87/41.31 for P/A/B/C. These remain reference variation, not verified
instrument noise. P's structured reference and radius/residual correlation
(-0.703 at guard 8, -0.501 at guard 12) leave background adequacy unresolved.
Changing to the existing guard-12 comparator retains B/C evidence; it does not
establish the owner's biological distinction.

The [full report](../validation/local/pnc-discrimination/reviewed-points-step6-dev4/report.html),
[all stages CSV](../validation/local/pnc-discrimination/reviewed-points-step6-dev4/stages.csv),
[B stage maps](../validation/local/pnc-discrimination/reviewed-points-step6-dev4/plots/B-maps-stages.png)
and [P profiles/reference histograms](../validation/local/pnc-discrimination/reviewed-points-step6-dev4/plots/P-profiles-histograms.png)
show enrichment and statistical detectability separately. No 4x threshold or other
new numerical rule was inferred, fitted or tested. Four qualitatively reviewed
locations in two previously examined DEVELOPMENT nuclei do not establish
accuracy or independent validation. A/B/C review is not an exhaustive negative
annotation; P confirmation is not an exact boundary annotation.

Checks: all ten saved P/A stage decisions are identical, saved support masks are
reused, all 20 stage masks stay inside the unchanged core, descriptive ratios
match bridge values exactly, and histogram counts/links pass. All **424 protected
files** remain hash-unchanged, including prior reports/arrays, review records and
the dev2 installer. New B8/B12/C8/C12 fit-only timings were
3.549/3.331/3.179/3.203 ms in an existing CPU Python process. P/A timing entries are
historical, not new measurements. These times exclude imports/loading, evidence,
rendering, cold app/SAM preparation and warm-slider work. No product test suite
rerun was needed for unchanged implementation.

Measured clean HEAD: `6adb2e6a14de7b89923345e69bc79f9018fb2af4`; unchanged
application source-tree Git hash: `8270e4af81e4955c21838f43c6bcecc451f37ebc`.
Step-6 ignored experiment SHA256:
`974f8357b659c2a0250522e6244e78345fcf6bfce79ab9248b5f90144a0e2e40`.
The fit/evidence hashes remain those recorded for steps 4/5 below; the
[frozen plan](../validation/local/pnc-discrimination/reviewed-points-step6-dev4/plan.json)
and [verification](../validation/local/pnc-discrimination/reviewed-points-step6-dev4/verification.json)
retain full configuration/input/protection provenance. No source, product/manual
call, dependency or installer changes; no validation measurement/reselection.

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
correction or seek to rescue the reviewed A/B/C locations. Step 6 confirms that
local statistical evidence alone can accept owner-reviewed nonconvincing B/C;
step 7 shows useful descriptive enrichment separation in the selected 12-target
panel, without establishing a cutoff or superiority over existing LocalContrast.
Review R02/R10 and reference-quality overlays before broader work. The observed
separations do not erase prior failures or validate a general detector. Plane
adequacy and structured-reference variation remain open issues. Stop at this
completed checkpoint; broader adoption, threshold fitting, hot-pixel rules and
dependency retries remain outside its scope.

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
