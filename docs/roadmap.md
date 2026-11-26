# Proposed next improvements

Manual correction is now available. The most valuable next work is to turn
reviewed cases into measurable accuracy evidence, then use that evidence to
guide model and detection changes.

| Priority | Proposed change | Benefit and validation needed |
| --- | --- | --- |
| 1 | Reviewed reference set and repeatable model benchmark | Export accepted nucleus labels and review PNC calls across representative HeLa/PC3M fields. Keep a held-out set; measure instance F1/IoU, count error, and PNC percentage error. This establishes whether a new model actually improves accuracy. |
| 2 | Explicit border/ROI rules and physical-unit thresholds | Consistently include/exclude partial nuclei, mitotic cells, and damaged regions. Read pixel-size calibration and express area in µm² so magnification changes do not silently change the phenotype. The two unmatched baseline objects were border nuclei. |
| 3 | Review queue and reasons/notes | Prioritize border objects, ambiguous shapes, low model confidence, and PNC counts near the cutoff. Add per-nucleus reasons, reviewer identity, and filters for flagged/unreviewed objects. Measure how much review effort this saves. |
| 4 | Model-assisted boundary refinement | Let a reviewer provide positive/negative points or a box to refine an existing mask, followed by manual acceptance. Benchmark the updated SAM backends on the reviewed set before changing defaults. Preserve the current offline polygon editor. |
| 5 | Distinct PNC puncta detection and manual PNC calls | The existing rule counts positive **pixels**, not individual PNCs. Add background correction, connected-object measurements, optional spot detection, and reviewer PNC+/PNC- overrides as separate, validated modes. Establish the biological rule first. |
| 6 | Resumable batch processing and clearer progress | Resume completed inputs with provenance checks, expose current-file progress and failure retry, and select timepoints/positions in the desktop interface. Preserve manual reviews when rerunning a model. |
| 7 | Installer/executable packaging | Provide a tested Windows installer with optional CPU/GPU model packs and offline setup. Test installation on clean machines; dependencies and checkpoint size dominate distribution size, even though application code is small. |
| 8 | 3D segmentation and temporal tracking | Use Z/time information when projection hides overlapping nuclei or puncta. This changes the measurement definition and needs separate 3D annotations and validation; it should not silently replace the current 2D workflow. |

A practical next milestone is priorities 1–3: review representative images,
define border inclusion, and create a queue of uncertain detections. The saved
correction history and label TIFFs now provide a foundation for that work.
