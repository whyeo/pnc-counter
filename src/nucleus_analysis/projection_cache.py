"""Reuse projections when changing measurements; invalidate on input/settings changes."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from .imaging import Projections, read_image
from .pnc_evidence import ALGORITHM, SCHEMA


def read_cached(path, config, axes=None, cache=None):
    if cache is None:
        return read_image(path, config, axes=axes)
    path = Path(path)
    stat = path.stat()
    # Input identity uses path, size and nanosecond mtime. Measurement thresholds
    # deliberately do not invalidate the projection. Masks have a content hash.
    needs_evidence = config.pnc_mode == "prominence" and config.pnc_z_policy == "auto"
    identity = {"schema": 2, "source": str(path.resolve()), "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns, "axes": axes,
                "reader": importlib.metadata.version("nd2" if path.suffix.lower() == ".nd2" else "tifffile"),
                "selection": [config.dapi_channel, config.pnc_channel,
                              config.time_index, config.position_index],
                "evidence": {"schema": SCHEMA, "algorithm": ALGORITHM,
                             "scale": [config.pixel_size_x_um, config.pixel_size_y_um]}
                            if needs_evidence else None}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    target = Path(cache) / "projections" / f"{key}.npz"
    if target.is_file():
        try:
            with np.load(target, allow_pickle=False) as data:
                return Projections(data["dapi_mean"], data["dapi_max"], data["pnc_max"],
                                   json.loads(str(data["metadata"])),
                                   {k[2:]: data[k] for k in data.files if k.startswith("z_")})
        except (OSError, ValueError, KeyError, EOFError):
            pass  # Interrupted/old cache: safely regenerate from the source.
    projections = read_image(path, config, axes=axes)
    target.parent.mkdir(parents=True, exist_ok=True)
    import uuid

    temporary = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, dapi_mean=projections.dapi_mean,
                            dapi_max=projections.dapi_max, pnc_max=projections.pnc_max,
                            metadata=json.dumps(projections.metadata),
                            **{"z_" + k: v for k, v in projections.pnc_evidence.items()})
    temporary.replace(target)
    return projections
