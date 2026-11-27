# Implemented workflows and next improvements

The four requested priorities have implementations in v0.4. See the
[accuracy workflow guide](accuracy-workflow.md) for definitions and limits.

| Requested priority | Implemented | Remaining scientific/user work |
| --- | --- | --- |
| 1. Reviewed references and accuracy measurements | Explicit verification, manual PNC calls, grouped validation/test references, instance and PNC metrics, count/percentage errors | Review representative biological fields and maintain a genuinely independent held-out set. Synthetic tests do not establish biological accuracy. |
| 2. Border rules and µm² thresholds | Border policy/margin, ND2/OME calibration, X/Y override, automatic nucleus bounds in µm², physical-area exports | Agree on border/mitotic/damaged-cell inclusion and appropriate area limits. |
| 3. Uncertainty review queue | Flag/border/cutoff/shape/area priority; filters/navigation; reviewer, notes and verified state | Measure review effort; retain SAM scores if calibrated confidence-based review is needed. Current priorities are heuristics. |
| 4. Candidate PNC spot counting | Separate mode, touching-spot splitting, size filtering, background subtraction, unique assignment, CSV/labels/overlays | Define biological puncta and validate noise, diffuse signal and projection effects on held-out fields. |

Desktop usability improvements implemented in v0.5 include file/folder drops,
immediate filename rows, raw previews, remembered channel/time/position choices,
Advanced settings, cached hardware detection with explicit redetection, automatic
accelerator selection, model downloads, named progress stages and projection caching.

Useful next engineering work:

1. Point/box prompts for model-assisted boundary refinement, keeping polygon
   editing and explicit acceptance of proposed changes.
2. Resumable batches, retrying selected failed images, and processing all selected
   time points/positions (the desktop currently analyzes one saved selection).
3. Code signing and a separate clean-machine check for the v0.6 Windows installer;
   optional fully offline PyTorch/model packs for labs without internet access.
4. Physical spot-size/spacing controls and cross-magnification validation.
5. Separate 3D segmentation/tracking when projection is insufficient; this
   changes the measurement definition and needs independent 3D annotations.
