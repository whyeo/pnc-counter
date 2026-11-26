"""Shape measurements compatible with the legacy feature definitions."""

import numpy as np
from scipy import ndimage as ndi
from skimage import morphology


def corrected_perimeter(mask):
    """Trace exterior pixel centers and use the Vossepoel–Smeulders estimator.

    MATLAB regionprops uses this chain-code estimator, rather than scikit-image's
    four-direction perimeter or Crofton perimeter. Holes are excluded.
    """
    padded = np.pad(mask, 1)
    labels, count = ndi.label(padded, structure=np.ones((3, 3)))
    total = 0.0
    # Clockwise Moore neighborhood, beginning west of the first boundary pixel.
    directions = np.array([(0, -1), (-1, -1), (-1, 0), (-1, 1),
                           (0, 1), (1, 1), (1, 0), (1, -1)])
    for label in range(1, count + 1):
        points = np.argwhere(labels == label)
        if len(points) < 2:
            continue
        start = tuple(points[0])
        current = start
        back = (start[0], start[1] - 1)
        boundary = [start]
        first_next = None
        for _ in range(8 * len(points) + 8):
            delta = np.array(back) - current
            k = int(np.flatnonzero(np.all(directions == delta, axis=1))[0])
            for step in range(8):
                direction = (k + step) % 8
                neighbor = tuple(np.array(current) + directions[direction])
                if labels[neighbor] == label:
                    back = tuple(np.array(current) + directions[(direction - 1) % 8])
                    break
            else:
                break
            if first_next is None:
                first_next = neighbor
            elif current == start and neighbor == first_next:
                break
            boundary.append(neighbor)
            current = neighbor
        else:
            raise ValueError("Boundary tracing did not converge")
        if boundary[-1] != boundary[0]:
            boundary.append(boundary[0])
        delta = np.diff(np.array(boundary), axis=0)**2
        if len(delta) > 1:
            corners = np.any(np.diff(np.vstack([delta, delta[0]]), axis=0), axis=1).sum()
            even = np.any(delta == 0, axis=1).sum()
            total += even * 0.980 + (len(delta) - even) * 1.406 - corners * 0.091
    return total


def legacy_circularity(mask, area):
    perimeter = corrected_perimeter(mask)
    # Algebraic form of MATLAB's pixel-center radius bias correction.
    return min(1.0, 4 * np.pi * area / (perimeter + np.pi)**2)


def legacy_solidity(mask):
    hull = morphology.convex_hull_image(mask)
    return float(np.count_nonzero(mask) / np.count_nonzero(hull))
