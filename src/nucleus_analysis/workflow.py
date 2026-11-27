"""Cheap acquisition inspection, conservative channel suggestions and raw previews."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from PIL import Image, ImageDraw


def inspect_image(path):
    path = Path(path)
    calibration = None
    if path.suffix.lower() == ".nd2":
        import nd2

        with nd2.ND2File(path) as reader:
            sizes = dict(reader.sizes)
            names = [c.channel.name for c in reader.metadata.channels or []]
            channels = reader.metadata.channels or []
            if channels and channels[0].volume is not None and all(channels[0].volume.axesCalibrated[:2]):
                voxel = reader.voxel_size()
                calibration = {"x": float(voxel.x), "y": float(voxel.y)}
    else:
        import tifffile

        with tifffile.TiffFile(path) as reader:
            series = reader.series[0]
            sizes = dict(zip(series.axes, series.shape))
            names = []
            if reader.ome_metadata:
                pixels = ElementTree.fromstring(reader.ome_metadata).find(".//{*}Pixels")
                if pixels is not None:
                    names = [c.get("Name") or c.get("ID", "") for c in pixels.findall("{*}Channel")]
                    factors = {"um": 1, "µm": 1, "μm": 1, "nm": .001, "mm": 1000}
                    calibration = {}
                    for axis in "XY":
                        value = pixels.get(f"PhysicalSize{axis}")
                        factor = factors.get(pixels.get(f"PhysicalSize{axis}Unit", "µm"))
                        if value is not None and factor:
                            calibration[axis.lower()] = float(value) * factor
                    if len(calibration) != 2:
                        calibration = None
    count = sizes.get("C", 1)
    if count < 2:
        raise ValueError("PNC analysis requires at least two declared channels (nuclei and marker)")
    if any(sizes[a] > 1 for a in sizes if a not in "TPCZYX"):
        raise ValueError("Unsupported acquisition axes; export a multichannel TIFF with explicit C/Y/X axes")
    names = [names[i] if i < len(names) and names[i] else f"Channel {i + 1}" for i in range(count)]
    # Names and dimensions distinguish saved acquisition mappings, not file names.
    signature = hashlib.sha256(json.dumps({"channels": names, "axes": sorted(sizes),
                                          "count": count, "time": sizes.get("T", 1),
                                          "positions": sizes.get("P", 1)}, sort_keys=True).encode()).hexdigest()
    return {"sizes": sizes, "channels": names, "signature": signature, "pixel_size_um": calibration}


def suggest_channels(metadata):
    names = [n.lower() for n in metadata["channels"]]
    dapi = [i for i, n in enumerate(names) if "dapi" in n or "hoechst" in n]
    pnc = [i for i, n in enumerate(names) if "pnc" in n or "ptbp1" in n]
    if len(dapi) == len(pnc) == 1 and dapi[0] != pnc[0]:
        return {"dapi_channel": dapi[0], "pnc_channel": pnc[0]}, True
    a = dapi[0] if len(dapi) == 1 else 0
    b = pnc[0] if len(pnc) == 1 and pnc[0] != a else next((i for i in range(len(names)) if i != a), 0)
    return {"dapi_channel": a, "pnc_channel": b}, False


def raw_preview(path, config, size=(600, 420)):
    """Read a representative plane, without segmentation or full-stack projection."""
    path = Path(path)
    if path.suffix.lower() == ".nd2":
        import nd2

        with nd2.ND2File(path) as reader:
            index = next(i for i, indices in enumerate(reader.loop_indices)
                         if indices.get("T", 0) == config.time_index
                         and indices.get("P", 0) == config.position_index)
            frame = reader.read_frame(index)
            if frame.ndim == 2:
                frame = frame[None]
            # ND2 returns views into its mmap. Own the selected planes before
            # closing the reader; accessing a closed mapping can crash Python.
            planes = [frame[c].copy() for c in (config.dapi_channel, config.pnc_channel)]
    else:
        import tifffile

        with tifffile.TiffFile(path) as reader:
            series = reader.series[0]
            # Read individual 2D pages when available. Unusual interleaved layouts
            # use the reader's supported array path, still off the Tk thread.
            axes, shape = series.axes, series.shape
            if not all(a in axes for a in "CYX"):
                raise ValueError("TIFF needs explicit C/Y/X axes; check the acquisition export")
            choices = {"T": config.time_index, "P": config.position_index}
            planes = []
            array = None
            for channel in (config.dapi_channel, config.pnc_channel):
                indices = tuple(slice(None) if a in "YX" else channel if a == "C"
                                else choices.get(a, 0) for a in axes)
                if axes.endswith("YX") and len(series.pages) == int(np.prod(shape[:-2])):
                    page = np.ravel_multi_index(indices[:-2], shape[:-2])
                    plane = series.pages[int(page)].asarray()
                else:
                    if array is None:
                        array = series.asarray()
                    plane = array[indices]
                planes.append(plane)
    tiles = []
    for plane, label in zip(planes, ("Nuclei / DAPI", "PNC marker")):
        lo, hi = np.percentile(plane, (1, 99.7))
        scaled = np.clip((plane.astype(float) - lo) * 255 / max(hi - lo, 1), 0, 255).astype("uint8")
        image = Image.fromarray(scaled).convert("RGB")
        image.thumbnail((size[0] // 2, size[1] - 30))
        tile = Image.new("RGB", (size[0] // 2, size[1]), "#202020")
        tile.paste(image, ((tile.width - image.width) // 2, 30))
        ImageDraw.Draw(tile).text((8, 8), label, fill="white")
        tiles.append(tile)
    result = Image.new("RGB", size)
    result.paste(tiles[0], (0, 0))
    result.paste(tiles[1], (size[0] // 2, 0))
    return result
