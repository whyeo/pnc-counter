"""Axis-aware readers and MATLAB-compatible intensity projections."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import AnalysisConfig


@dataclass
class Projections:
    dapi_mean: np.ndarray
    dapi_max: np.ndarray
    pnc_max: np.ndarray
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        arrays = (self.dapi_mean, self.dapi_max, self.pnc_max)
        if any(a.ndim != 2 or a.shape != self.dapi_max.shape for a in arrays):
            raise ValueError("Projections must be matching two-dimensional images")
        for array in arrays:
            _check_image(array)
        if self.dapi_max.dtype != np.uint8 or self.dapi_mean.max() > 255:
            raise ValueError("DAPI maximum must be uint8 and mean intensities must be in [0, 255]")


def scale_uint8(image):
    image = np.asarray(image, dtype=np.float64)
    lo, hi = float(image.min()), float(image.max())
    if hi == lo:
        return np.zeros(image.shape, dtype=np.uint8)
    # MATLAB uint8 conversion rounds halves upward, unlike numpy's astype.
    return np.floor((image - lo) * (255.0 / (hi - lo)) + 0.5).astype(np.uint8)


def _check_image(array):
    real_numeric = (np.issubdtype(array.dtype, np.integer)
                    or np.issubdtype(array.dtype, np.floating))
    if array.size == 0 or not real_numeric:
        raise ValueError("Image must be a nonempty numeric array")
    if not np.isfinite(array).all() or np.any(array < 0):
        raise ValueError("Image intensities must be finite and nonnegative")


def project_array(array, axes, config=None, metadata=None):
    """Project explicitly named axes; never guess channel/time dimensions.

    C denotes channel, Z depth, T time, P position, and Y/X spatial axes.
    TIFF S (RGB samples) and unknown nonsingleton axes are rejected.
    """
    config = config or AnalysisConfig()
    array = np.asarray(array)
    axes = axes.upper()
    if len(axes) != array.ndim or len(set(axes)) != len(axes):
        raise ValueError("axes must contain one unique name per array dimension")
    for axis, index in (("T", config.time_index), ("P", config.position_index)):
        if axis in axes:
            dim = axes.index(axis)
            if index >= array.shape[dim]:
                raise ValueError(f"{axis} index {index} is out of range")
            array = np.take(array, index, axis=dim)
            axes = axes.replace(axis, "")
        elif index:
            raise ValueError(f"Image has no {axis} axis; index must be zero")
    for axis in list(axes):
        if axis not in "ZCYX":
            dim = axes.index(axis)
            if array.shape[dim] != 1:
                raise ValueError(f"Unsupported nonsingleton axis {axis!r}; use an explicit axes layout")
            array = np.take(array, 0, axis=dim)
            axes = axes.replace(axis, "")
    if not all(axis in axes for axis in "CYX"):
        raise ValueError("Image must contain C, Y, and X axes")
    if "Z" not in axes:
        array = array[np.newaxis]
        axes = "Z" + axes
    array = np.transpose(array, [axes.index(axis) for axis in "ZCYX"])
    _check_image(array)
    if max(config.dapi_channel, config.pnc_channel) >= array.shape[1]:
        raise ValueError(f"Requested channel does not exist (image has {array.shape[1]} channels)")
    dapi = array[:, config.dapi_channel]
    return Projections(
        scale_uint8(dapi).mean(axis=0),
        scale_uint8(dapi.max(axis=0)),
        array[:, config.pnc_channel].max(axis=0),
        metadata or {},
    )


def read_image(path, config=None, axes=None):
    """Read ND2 one acquisition frame at a time; TIFF uses its declared axes."""
    config = config or AnalysisConfig()
    path = Path(path)
    if path.suffix.lower() == ".nd2":
        import nd2

        with nd2.ND2File(path) as reader:
            sizes = dict(reader.sizes)
            if config.time_index >= sizes.get("T", 1):
                raise ValueError("time_index is out of range")
            if config.position_index >= sizes.get("P", 1):
                raise ValueError("position_index is out of range")
            unknown = set(sizes) - set("TPCZYX")
            if any(sizes[a] > 1 for a in unknown):
                raise ValueError(f"Unsupported ND2 axes: {unknown}")
            if max(config.dapi_channel, config.pnc_channel) >= sizes.get("C", 1):
                raise ValueError("Requested channel does not exist")
            dapi_sum = None
            n_planes = 0
            dapi_min, dapi_hi = np.inf, -np.inf
            # DAPI stack scaling is quantized before the mean in the old app.
            # Two streaming passes preserve that behavior without holding a Z stack.
            selected = [i for i, idx in enumerate(reader.loop_indices)
                        if idx.get("T", 0) == config.time_index
                        and idx.get("P", 0) == config.position_index]
            if not selected:
                raise ValueError("No frames match the requested time/position")
            for i in selected:
                frame = reader.read_frame(i)
                if frame.ndim == 2:
                    frame = frame[None]
                _check_image(frame)
                dapi = frame[config.dapi_channel]
                pnc = frame[config.pnc_channel]
                dapi_min = min(dapi_min, float(dapi.min()))
                dapi_hi = max(dapi_hi, float(dapi.max()))
                if n_planes == 0:
                    dapi_max, pnc_max = dapi.copy(), pnc.copy()
                    dapi_sum = np.zeros(dapi.shape, dtype=np.float64)
                else:
                    np.maximum(dapi_max, dapi, out=dapi_max)
                    np.maximum(pnc_max, pnc, out=pnc_max)
                n_planes += 1
            if dapi_hi > dapi_min:
                factor = 255.0 / (dapi_hi - dapi_min)
                for i in selected:
                    frame = reader.read_frame(i)
                    if frame.ndim == 2:
                        frame = frame[None]
                    dapi_sum += np.floor((frame[config.dapi_channel].astype(float) - dapi_min)
                                         * factor + 0.5)
            metadata = {"source": str(path.resolve()), "sizes": sizes,
                        "channels": [c.channel.name for c in reader.metadata.channels or []],
                        "time_index": config.time_index, "position_index": config.position_index}
            channels = reader.metadata.channels or []
            volume = channels[config.dapi_channel].volume if len(channels) > config.dapi_channel else None
            if volume is not None and all(volume.axesCalibrated[:2]):
                voxel = reader.voxel_size()
                metadata["pixel_size_um"] = {"x": float(voxel.x), "y": float(voxel.y)}
            return Projections(dapi_sum / n_planes, scale_uint8(dapi_max), pnc_max, metadata)
    if path.suffix.lower() in (".tif", ".tiff"):
        import tifffile

        with tifffile.TiffFile(path) as reader:
            series = reader.series[0]
            metadata = {"source": str(path.resolve()), "axes": axes or series.axes}
            if reader.ome_metadata:
                from xml.etree import ElementTree

                pixels = ElementTree.fromstring(reader.ome_metadata).find(".//{*}Pixels")
                sizes = {}
                factors = {"um": 1, "µm": 1, "μm": 1, "nm": 0.001, "mm": 1000}
                if pixels is not None:
                    for axis in ("X", "Y"):
                        value = pixels.get(f"PhysicalSize{axis}")
                        factor = factors.get(pixels.get(f"PhysicalSize{axis}Unit", "µm"))
                        if value is not None and factor is not None:
                            sizes[axis.lower()] = float(value) * factor
                if len(sizes) == 2:
                    metadata["pixel_size_um"] = sizes
            return project_array(series.asarray(), axes or series.axes, config,
                                 metadata)
    raise ValueError("Supported input formats: .nd2, .tif, .tiff")
