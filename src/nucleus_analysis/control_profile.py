"""Optional development-negative incidental-signal profiles with strict provenance.

Profiles summarize *automatic* nucleus maxima; field quantiles avoid pretending
thousands of correlated pixels are independent controls. No calibrated biological
false-positive rate is claimed. Incompatible or sparse profiles explicitly fall
back to uncalibrated enrichment.
"""

import hashlib
import json
from collections import defaultdict

SCHEMA = 1


def protocol_key(protocol):
    return hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()


def fit_profiles(controls, protocol, *, minimum_fields=2):
    import numpy as np

    grouped = defaultdict(list)
    for control in controls:
        if control["split"] != "development":
            raise ValueError("Only development controls may fit an incidental-signal profile")
        if control.get("role") != "negative_control":
            raise ValueError("Profile fitting requires explicitly selected negative controls")
        scores = control["automatic_nucleus_maxima"]
        if scores:
            if not np.isfinite(scores).all() or min(scores) < 0:
                raise ValueError("Control scores must be finite and nonnegative")
            grouped[control["acquisition_signature"]].append({
                "field": control["field"], "source_sha256": control["source_sha256"],
                "nuclei": len(scores), "q95_automatic_nucleus_max": float(np.quantile(scores, .95))})
    profiles, unavailable = {}, {}
    for signature, fields in grouped.items():
        if len({f["field"] for f in fields}) != len(fields):
            raise ValueError("Duplicate control field in profile")
        if len(fields) < minimum_fields:
            unavailable[signature] = {"reason": "insufficient compatible development fields", "fields": fields}
        else:
            profiles[signature] = {"fields": fields, "floor": max(f["q95_automatic_nucleus_max"] for f in fields)}
    return {"schema": SCHEMA, "protocol": protocol, "protocol_sha256": protocol_key(protocol),
            "profiles": profiles, "unavailable": unavailable, "minimum_fields": minimum_fields,
            "operating_rule": "max(uncalibrated signal cutoff, max compatible-field q95 nucleus maximum)",
            "claim": "incidental detector-signal reference; not a biological FPR or probability"}


def compatible_floor(profile, acquisition_signature, protocol):
    if profile.get("schema") != SCHEMA or profile.get("protocol_sha256") != protocol_key(protocol):
        return None, "fallback: incompatible profile schema or scoring protocol"
    value = profile.get("profiles", {}).get(acquisition_signature)
    if value is None:
        return None, "fallback: no sufficiently replicated acquisition-compatible development controls"
    return float(value["floor"]), "compatible development incidental-signal profile"
