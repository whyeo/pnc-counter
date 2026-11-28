# v0.7 exploration: BEFORE dev2 / AFTER dev4

**Decision: no-go for changing the default detector or finalizing v0.7.**
The audit explains losses and the new measurements recover calls, but the
predeclared comparisons do not resolve negative-group signal versus positive/small
preservation. No biological accuracy improvement is established.

Stable remains **v0.6.0**. The last packaged local installer remains
**0.7.0.dev2**. **0.7.0.dev4 is source-only research work**, with no new product
method, UI expansion or installer. Existing protocols, slider, overrides, revisions
and preview preferences are preserved. No push, tag, merge or publication is authorized.

## Exact versions and reproducibility

| Role | Version | Full source commit |
| --- | --- | --- |
| Stable legacy rule replay | 0.6.0 | `d56e429a448ea8b95a70140260573391c36d7c12` |
| BEFORE preview | 0.7.0.dev2 | `f53cf62912b6188f7886af3c72a1689119888a0f` |
| Loss audit tooling | 0.7.0.dev3 | `55ad2501789161aa3f69952997ac008064868370` |
| Preserved initial range experiment | 0.7.0.dev3 | `e45b19775c32fbdd038990d81a61f6669e0ad0db` |
| AFTER measured implementation | 0.7.0.dev4 | `dec0c50a8c2414757e9638145da02ea1e0c37c41` |

Development and validation ran from clean source. Their JSON records include every
source-file hash and dirty state. The stable threshold function is compiled from
the exact stable Git object; dev2 detector source is checked unchanged. Only the
PNC rules are compared: nucleus segmentation is not rerun.

The full private report is
`validation/local/pnc-discrimination/v070-dev4/exploration-60-40/report.html`.
It includes all declared curves, per-field/nucleus counts, paired changes,
candidate-stage attrition, mixture outcomes, acquisition metadata, source hashes,
matched raw/overlay views for **all 37 fields**, Z views, runtime and functional
checks. All microscopy data/results remain ignored and local. Dev2's existing
installer/report/provenance are protected by content hashes and unchanged.

## New split and acquisition limitations

The owner changed new work to approximately 60/40. Seed `20261128` gives:

| Group | Development fields | Validation fields |
| --- | ---: | ---: |
| Negative | 6 | 4 |
| Positive | 10 | 7 |
| Small PNC | 6 | 4 |
| Total | 22 | 15 |

The retained SAM masks, exclusions and automatic-call denominators are identical
across methods. Manual overrides/effective calls are exported separately; overrides
are excluded from control-profile fitting. No fields are dropped for a better rate.

No specimen or related-field IDs are supplied. One ND2 acquisition is therefore the
available unit, with all its Z planes/time/position/nuclei together. Shared capture
dates/settings are batches, not proof of specimen independence. All HeLa fields
were examined previously: reshuffling does not create independent validation.

Metadata shows marker exposures of **300/400/600 ms** for negatives,
**90/100/200 ms** for positives, and **90 ms** for small-PNC fields, at recorded
gain 1x. The channels are DAPI and TxRED; molecular marker identity is unknown and
no separate nucleolar channel is present. Acquisition equivalence is not assumed,
and DAPI-dark regions are not identified as nucleoli.

## FIRST: dev2 loss diagnosis

Exact baseline instrumentation was checked for candidate/label/score parity.
Fifteen named one-factor variants were evaluated on six predefined development
fields (two/group, including the owner-cited small IMG9). They independently test
noise floor, reference max/min/local choice, score min/max, support extraction,
area/extent/boundary gates, candidate-count penalty and Z treatment.

At dev2 sensitivity 25, the 237 nuclei in these six fields were classified as:

- 152 with low-scored candidates;
- 78 with a pre-penalty candidate crossing below the cutoff after the count penalty;
- one with an above-cutoff score suppressed by a hard rule;
- six accepted.

Fourteen smoothed peaks were discarded because raw support omitted the smoothed
maximum pixel. Small IMG9 had 2,200 returned candidates, three discarded anchors
and 59 sub-three-pixel support flags. Disabling the size minimum alone left its
strict calls at 1/29; removing the count penalty changed them to 4/29. The support
hypothesis is real but does not explain most strict-setting losses.

Field means on the same six audit fields illustrate the trade-offs:

| Version / diagnostic | Negative | Positive | Small |
| --- | ---: | ---: | ---: |
| BEFORE dev2, sensitivity 25 | 0.00% | 4.35% | 1.72% |
| AFTER dev3 audit: penalty removed only | 3.33% | 63.05% | 6.90% |
| AFTER dev3 audit: score max instead of min only | 26.32% | 92.24% | 6.90% |
| AFTER dev3 audit: connected growth only | 0.00% | 20.46% | 0.00% |
| AFTER dev3 audit: hard Z score | 0.00% | 0.68% | 0.00% |

These locate numerical losses; they are not reviewed true-focus classifications.
The full report supplies every ablation, four original sensitivity points and
candidate records, including raw-anchor losses hidden by the production method.

## Bounded proposed methods

**A: enrichment.** An intranuclear 20th–80th-percentile reference excludes bright
structures and low tails from the reference. Reference-masked smoothing estimates
local background. Permissive seeds are compared using half-height support or
lower-threshold connected growth at 15% of peak. Local contrast, nuclear contrast,
signed/positive integrated excess, raw support/size and warning flags are exported
separately. The score is signed local excess divided by nuclear reference and
square-root support area. Morphology and Z support do not zero the score.

**B: optional control profile.** At least two development negative fields must
match the acquisition signature and scoring protocol. The profile uses per-field
95th-percentile automatic nucleus maxima. It is an incidental-signal reference,
not a calibrated biological false-positive rate. There were **zero usable profiles
for the 15 validation fields** under the declared replication/compatibility rule;
B falls back to A-growth. Its equal rates are not a calibration efficacy result.

**C: intensity-mixture diagnostic.** One versus two Gaussian components are
compared with a BIC margin of 10, three fixed starts, at most 80 iterations and
1,024 deterministic spatial samples per nucleus. Constant, nonconvergent or weak
fits provide no mixture-derived signal. Tiny upper tails need not form a second
component. Pixels remain correlated; component weights/responsibilities and BIC
do not identify PNCs or provide biological probabilities.

The dev3 development-only range, `0.1 * 20 ** (1-sensitivity/100)`, called nearly
all nuclei at every declared A point. That failed sweep and its freeze are
preserved. **Before any new validation measurement**, a single dev4 amendment
broadened the mapping to `0.1 * 1000 ** (1-sensitivity/100)`. Preparation/selection
function ASTs stayed unchanged; there was no second range amendment.

Dev4 declared sensitivities **0, 25, 50, 75, 100**, giving score cutoffs
**100, 17.783, 3.162, 0.562, 0.1**. Development froze A-half/A-growth/B at 50 and
C at 75. All fixed diagnostic curve points are reported, but no validation result
was used to reselect a threshold. Technical parameters and the objective are in
the comparison plan; this was not a combinatorial search.

## BEFORE / AFTER on the SAME validation split

Each cell gives **field-averaged call percentage (positive/total nuclei)**. Pooled
percentages and field distributions are separate in the private report. Folder
labels do not provide sensitivity, specificity, accuracy or per-cell truth.

| Role / exact version / configuration | Negative: 4 fields | Positive: 7 fields | Small: 4 fields |
| --- | ---: | ---: | ---: |
| BEFORE v0.6.0 legacy, 10 pixels | 28.82% (33/114) | 82.99% (243/290) | 8.45% (9/127) |
| BEFORE 0.7.0.dev2 adaptive, s50 | 24.65% (28/114) | 83.80% (247/290) | 21.53% (26/127) |
| BEFORE 0.7.0.dev2 prominence, s25, rejected | 0.00% (0/114) | 2.25% (6/290) | 1.14% (1/127) |
| BEFORE 0.7.0.dev2 prominence, s50 | 7.85% (9/114) | 50.99% (153/290) | 3.88% (4/127) |
| AFTER 0.7.0.dev4 A-half, frozen s50 | 34.51% (39/114) | 87.51% (255/290) | 16.49% (17/127) |
| AFTER 0.7.0.dev4 A-growth, frozen s50 | 40.56% (46/114) | 88.66% (258/290) | 15.45% (16/127) |
| AFTER 0.7.0.dev4 B, fallback, frozen s50 | 40.56% (46/114) | 88.66% (258/290) | 15.45% (16/127) |
| AFTER 0.7.0.dev4 C-mixture, frozen s75 | 39.10% (45/114) | 89.97% (259/290) | 37.65% (47/127) |

A-growth versus legacy changes field means by **+11.74 / +5.67 / +7.00 percentage
points** (negative / positive / small). Higher positive/small-folder rates arrive
alongside higher negative-group calls. No proposed frozen point passed the
development proxy screen. Additional calls do not establish biological recovery.

## Secondary SAM boundary probe

Six predeclared crops used the already installed official SAM2.1 Tiny checkpoint,
CPU/four threads, with point-only and box-only prompts. No model/dependency was
downloaded or trained, and no output influenced masks or PNC calls. Point-only
masks occupied 9,380/9,409 and 9,407/9,409 pixels in the two small-PNC probes;
box-only masks occupied 782 and 174 pixels. Prompt-dependent boundaries do not
establish biological recognition. SAM mask-quality output is not PNC confidence.

## Performance and regression evidence

BEFORE dev2: **152 passing tests**. AFTER dev4: **163 passing tests**, Ruff passes.
New tests cover baseline instrumentation parity, retained/discarded candidates,
growth support, gain/weak noise/hot-pixel diagnostics, monotonic cached selection,
supporting Z, mixture fallbacks, profile incompatibility, development-only fitting,
fixed denominators and automatic/manual-call separation. Existing compatibility,
latest-request, revision/profile and installer guards remain tested.

On a Ryzen 7 5700X/Windows 10, 1040 x 1392 fields, the same existing prominence
review controller gave these warm median/p95 times (seconds):

| Field | BEFORE 0.7.0.dev2 | AFTER 0.7.0.dev4 |
| --- | ---: | ---: |
| Negative example | 0.465 / 0.490 | 0.465 / 0.481 |
| Positive example | 0.589 / 0.621 | 0.589 / 0.621 |
| Small example | 0.512 / 0.542 | 0.512 / 0.527 |

These include debounce, polling and Tk/Pillow rendering in withdrawn windows.
The positive/small example medians exceed the 0.5-second target; p95 stayed under
one second. The controller did not change, so no responsiveness improvement is
claimed. Each run saved/reopened a new revision, retained geometry and blocked SAM.

Cold/first feature preparation from saved projections and warm research selection
plus Pillow rendering are separately recorded in the full report. OS disk cache
was uncontrolled and some verification processes overlapped. Research timings do
not imply that A/B/C were added to the product slider. All PNC work remains on CPU.

## Next recommendation and reproduction

Keep the legacy default and dev2 installer. Use the full report for an optional
short review of obvious small/clear signals, missed calls and negative-group
structures. Confirm marker identity and specimen relationships; evaluate optional
calibration only with acquisition-compatible development controls. Do not retune
against this validation set. Fresh independent specimens/fields would be needed
for stronger generalization claims, but were not a prerequisite for this audit.

For a new local run, use a new output directory and preserve completed phases:

```powershell
python tools/pnc_loss_audit.py plan --previous-split validation/local/pnc-discrimination/heldout-30-70/split.json --output validation/local/new-60-40
python tools/pnc_loss_audit.py audit --output validation/local/new-60-40
python -m tools.enrichment_experiment plan --output validation/local/new-60-40
python -m tools.enrichment_experiment development --output validation/local/new-60-40
python -m tools.enrichment_experiment validation --output validation/local/new-60-40
```

Baseline ideas consulted: [Big-FISH spot detection](https://big-fish.readthedocs.io/en/stable/detection/spots.html),
[mixture model selection](https://scikit-learn.org/stable/auto_examples/mixture/plot_gmm_selection.html),
and [Micro-SAM](https://github.com/computational-cell-analytics/micro-sam). The
actual optional probe used existing official SAM2.1, not a new microscopy model.
