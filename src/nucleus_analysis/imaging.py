"""Axis-aware readers and MATLAB-compatible intensity projections."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import AnalysisConfig
from .pnc_evidence import PlaneEvidence, evidence_metadata, validate_evidence


@dataclass
class Projections:
    dapi_mean: np.ndarray
    dapi_max: np.ndarray
    pnc_max: np.ndarray
    metadata: dict = field(default_factory=dict)
    pnc_evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        arrays = (self.dapi_mean, self.dapi_max, self.pnc_max)
        if any(a.ndim != 2 or a.shape != self.dapi_max.shape for a in arrays):
            raise ValueError("Projections must be matching two-dimensional images")
        for array in arrays:
            _check_image(array)
        if self.dapi_max.dtype != np.uint8 or self.dapi_mean.max() > 255:
            raise ValueError("DAPI maximum must be uint8 and mean intensities must be in [0, 255]")
        validate_evidence(self.pnc_evidence, self.metadata, self.pnc_max.shape)
        for array in self.pnc_evidence.values():
            array.flags.writeable = False


def scale_uint8(image):
    image = np.asarray(image, dtype=np.float64)
    lo, hi = float(image.min()), float(image.max())
    if hi == lo:
        return np.zeros(image.shape, dtype=np.uint8)
    # MATLAB uint8 conversion rounds halves upward, unlike numpy's astype.
    return np.floor((image - lo) * (255.0 / (hi - lo)) + 0.5).astype(np.uint8)


def display_uint8(image, limits=None):
    """Display-only contrast; explicit raw limits allow comparisons across fields."""
    lo, hi = np.percentile(image, (1, 99.7)) if limits is None else limits
    if not np.isfinite([lo, hi]).all() or (limits is not None and hi <= lo):
        raise ValueError("Display maximum must exceed minimum; both must be finite")
    return np.clip((image.astype(float) - lo) * 255 / max(hi - lo, 1e-12), 0, 255).astype(np.uint8)


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
    metadata = dict(metadata or {})
    metadata.update(time_index=config.time_index, position_index=config.position_index,
                    dapi_channel=config.dapi_channel, pnc_channel=config.pnc_channel,
                    representation="maximum Z projection", z_planes=array.shape[0])
    evidence = {}
    if config.pnc_mode == "prominence" and config.pnc_z_policy == "auto":
        from .phenotype import pixel_size

        builder = PlaneEvidence(pixel_size(config, metadata))
        for z, plane in enumerate(array[:, config.pnc_channel]):
            builder.add(plane, z)
        evidence = builder.finish()
        metadata["pnc_evidence"] = evidence_metadata(builder.count, metadata.get("z_spacing_um"), builder.calibration)
    return Projections(
        scale_uint8(dapi).mean(axis=0),
        scale_uint8(dapi.max(axis=0)),
        array[:, config.pnc_channel].max(axis=0),
        metadata, evidence,
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
            builder = None
            if config.pnc_mode == "prominence" and config.pnc_z_policy == "auto":
                channels = reader.metadata.channels or []
                volume = channels[config.pnc_channel].volume if len(channels) > config.pnc_channel else None
                calibration = None
                if config.pixel_size_x_um is not None:
                    calibration = (config.pixel_size_x_um, config.pixel_size_y_um)
                elif volume is not None and all(volume.axesCalibrated[:2]):
                    voxel = reader.voxel_size()
                    calibration = (float(voxel.x), float(voxel.y))
                builder = PlaneEvidence(calibration)
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
                if builder is not None:
                    builder.add(pnc, n_planes)
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
                        "time_index": config.time_index, "position_index": config.position_index,
                        "dapi_channel": config.dapi_channel, "pnc_channel": config.pnc_channel,
                        "representation": "maximum Z projection", "z_planes": n_planes}
            channels = reader.metadata.channels or []
            volume = channels[config.dapi_channel].volume if len(channels) > config.dapi_channel else None
            if volume is not None and all(volume.axesCalibrated[:2]):
                voxel = reader.voxel_size()
                metadata["pixel_size_um"] = {"x": float(voxel.x), "y": float(voxel.y)}
                if len(volume.axesCalibrated) > 2 and volume.axesCalibrated[2]:
                    metadata["z_spacing_um"] = float(voxel.z)
            if builder is not None:
                metadata["pnc_evidence"] = evidence_metadata(n_planes, metadata.get("z_spacing_um"), builder.calibration)
            return Projections(dapi_sum / n_planes, scale_uint8(dapi_max), pnc_max, metadata,
                               builder.finish() if builder is not None else {})
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
                    for axis in ("X", "Y", "Z"):
                        value = pixels.get(f"PhysicalSize{axis}")
                        factor = factors.get(pixels.get(f"PhysicalSize{axis}Unit", "µm"))
                        if value is not None and factor is not None:
                            sizes[axis.lower()] = float(value) * factor
                if "x" in sizes and "y" in sizes:
                    metadata["pixel_size_um"] = {k: sizes[k] for k in ("x", "y")}
                if "z" in sizes:
                    metadata["z_spacing_um"] = sizes["z"]
            return project_array(series.asarray(), axes or series.axes, config,
                                 metadata)
    raise ValueError("Supported input formats: .nd2, .tif, .tiff")


def read_marker_plane(path, config, z_index):
    """An inspection-only plane; reading it never changes a projection or protocol."""
    path = Path(path)
    if path.suffix.lower() == ".nd2":
        import nd2

        with nd2.ND2File(path) as reader:
            selected = [i for i, idx in enumerate(reader.loop_indices)
                        if idx.get("T", 0) == config.time_index and idx.get("P", 0) == config.position_index]
            if not 0 <= z_index < len(selected):
                raise ValueError("Z plane out of range")
            frame = reader.read_frame(selected[z_index])
            return (frame if frame.ndim == 2 else frame[config.pnc_channel]).copy()
    import tifffile

    with tifffile.TiffFile(path) as reader:
        series = reader.series[0]
        axes = series.axes
        choices = {"T": config.time_index, "P": config.position_index, "Z": z_index, "C": config.pnc_channel}
        if z_index and "Z" not in axes:
            raise ValueError("Image has no Z axis")
        indices = tuple(slice(None) if a in "YX" else choices.get(a, 0) for a in axes)
        if axes.endswith("YX") and len(series.pages) == int(np.prod(series.shape[:-2])):
            index = np.ravel_multi_index(indices[:-2], series.shape[:-2])
            return series.pages[int(index)].asarray().copy()
        return series.asarray()[indices].copy()
