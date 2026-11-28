"""Spatial display numbers without changing persistent mask identities."""

import math
import statistics

ALGORITHM = "centroid-reading-rows-v1"


def spatial_numbering(rows):
    """Return display-number rows and the vertical row tolerance, in pixels.

    Start each approximate row at its topmost remaining centroid. Include centers
    within half the median area-equivalent nucleus diameter, then read left to
    right. Anchoring each row prevents chains of staggered cells merging rows.
    Inclusion/PNC state never affects numbering; geometry edits can renumber it.
    Centroids use the same one-based coordinates as exported measurements.
    """
    rows = list(rows)
    if not rows:
        return [], 0.
    tolerance = max(1., statistics.median(math.sqrt(4 * r["Area"] / math.pi) for r in rows) / 2)
    remaining = sorted(rows, key=lambda r: (r["CentroidY"], r["CentroidX"], r["MaskID"]))
    mapped = []
    start = 0
    row_number = 0
    while start < len(remaining):
        row_number += 1
        stop = start + 1
        top = remaining[start]["CentroidY"]
        while stop < len(remaining) and remaining[stop]["CentroidY"] <= top + tolerance:
            stop += 1
        for row in sorted(remaining[start:stop], key=lambda r: (r["CentroidX"], r["CentroidY"], r["MaskID"])):
            mapped.append({"DisplayNumber": len(mapped) + 1, "MaskID": int(row["MaskID"]),
                           "Row": row_number, "CentroidX": float(row["CentroidX"]),
                           "CentroidY": float(row["CentroidY"])})
        start = stop
    return mapped, tolerance
