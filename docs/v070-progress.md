# PNC Counter v0.7 progress

Updated 28 November 2026. This tracker records completed research, unresolved
findings and the next approved work. **A completed experiment does not mean that
its detector is ready for adoption.**

Stable download: **v0.6.0**. Latest local installer: **0.7.0.dev2**.
Latest measured research source: **0.7.0.dev4**, commit
`5df32d0fcb2f012bf870e33c145cd1119e3cfccf`.
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
| Step 5A: inspect the real small example | In progress | Fixed small IMG9/n23 anchor inspection; experiment SAG5A-dev4-r1-20261128 is being declared on a clean documentation checkpoint. | Explain signal, background and reference-width contributions without assuming the selected anchor is a true PNC. |
| Step 5B: one expanded-guard comparison | Pending; approved after 5A | One larger central exclusion will be frozen before its outputs are inspected; all other step-4 settings remain fixed. | Measure reference contamination, fit adequacy, signal retention and failures with other rules fixed. |
| Automatic full-field integration and wider validation | Deferred | Current work remains diagnostic research. | Review step 5 before expanding candidate generation, adding rejection rules or measuring validation again. |
| Final v0.7 release | Pending owner approval | No release, tag or promotion authorized. | Demonstrate useful real-image behavior and complete owner testing. |

## Next approved checkpoint

The v0.7 agent owns execution and report updates; the bridge agent maintains the
handoff and release boundary. The owner approved this next step on 28 November.

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
| Small example and guard step 5 | Approved; experiment ID to be declared | Pending |
