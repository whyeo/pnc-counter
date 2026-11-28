"""Compact per-plane marker evidence. No stack, nucleus model, or GPU is retained."""

import numpy as np
from scipy import ndimage as ndi

ALGORITHM = "plane-local-prominence-v1"
SCHEMA = 1


def scales(calibration):
    if calibration is None:
        return ((.75, .75), (1.5, 1.5), (3., 3.)), (10., 10.)
    x, y = calibration
    return (tuple(tuple(float(np.clip(s / v, .5, 6)) for v in (y, x))
                  for s in (.10, .20, .40)),
            tuple(float(np.clip(1.5 / v, 4, 40)) for v in (y, x)))


class PlaneEvidence:
    """Keep the best locally supported score and its plane, using O(YX) memory.

    Raw support prevents a smoothed hot pixel from becoming a multi-pixel spot.
    The 2% background floor bounds evidence when MAD noise approaches zero.
    No requirement for a punctum to span multiple Z planes is made.
    """

    def __init__(self, calibration=None):
        self.calibration = calibration
        self.arrays = {}
        self.count = 0

    def add(self, image, index):
        values = image.astype(np.float32)
        small, broad = scales(self.calibration)
        background = ndi.gaussian_filter(values, broad)
        residual = values - background
        center = float(np.median(residual))
        noise = 1.4826 * float(np.median(np.abs(residual - center)))
        floor = np.maximum(.02 * background, max(noise, float(values.max()) * 1e-6, 1e-12))
        response = np.maximum.reduce([ndi.gaussian_filter(values, s) - background for s in small])
        score = np.maximum(0, np.minimum(response, residual - center) / floor)
        if not self.arrays:
            self.arrays = {"score": np.zeros(values.shape, np.float32),
                           "plane": np.full(values.shape, -1, np.int32)}
        active = score > self.arrays["score"]
        self.arrays["score"][active] = score[active]
        self.arrays["plane"][active] = index
        self.count += 1

    def finish(self):
        return self.arrays


def evidence_metadata(count, z_spacing=None, calibration=None):
    return {"schema": SCHEMA, "algorithm": ALGORITHM, "planes": count,
            "z_spacing_um": z_spacing, "calibration_um": calibration,
            "policy": "best per-plane local prominence; no continuity gate"}


def selected_evidence(projections, config):
    if config.pnc_z_policy == "projection" or not projections.pnc_evidence:
        return {}
    from .phenotype import pixel_size

    current = pixel_size(config, projections.metadata)
    recorded = projections.metadata["pnc_evidence"].get("calibration_um")
    if (list(current) if current else None) != (list(recorded) if recorded else None):
        raise ValueError("Z evidence uses a different pixel scale. Reload Z evidence or choose the projection Z policy.")
    return projections.pnc_evidence


def validate_evidence(arrays, metadata, shape):
    if not arrays:
        return
    info = metadata.get("pnc_evidence", {})
    if info.get("schema") != SCHEMA or info.get("algorithm") != ALGORITHM:
        raise ValueError("Unsupported PNC Z evidence; regenerate from the source or use projection mode")
    if set(arrays) != {"score", "plane"} or any(a.shape != shape for a in arrays.values()):
        raise ValueError("PNC Z evidence shape/keys do not match the projections")
    if not np.isfinite(arrays["score"]).all() or np.any(arrays["score"] < 0):
        raise ValueError("Invalid PNC Z scores")
    plane = arrays["plane"]
    if not np.issubdtype(plane.dtype, np.integer) or np.any(plane < -1) or np.any(plane >= info["planes"]):
        raise ValueError("Invalid PNC Z plane indices")
