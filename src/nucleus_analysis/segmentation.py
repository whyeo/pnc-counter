"""SAM backends, lightweight fallback, and portable candidate-mask storage."""

import hashlib
import json
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from skimage import feature, filters, morphology, segmentation


def _filter_candidates(candidates, config):
    return [idx for idx in candidates
            if config.min_nucleus_area <= len(idx) <= config.max_nucleus_area]


def _rle_indices(rle):
    """Convert SAM's column-major RLE directly to row-major flat pixel indices."""
    h, w = rle["size"]
    offset = 0
    pieces = []
    for i, count in enumerate(rle["counts"]):
        if i % 2 and count:
            linear = np.arange(offset, offset + count, dtype=np.int64)
            pieces.append((linear % h) * w + linear // h)
        offset += count
    return np.sort(np.concatenate(pieces)) if pieces else np.empty(0, dtype=np.int64)


class Segmenter:
    """Load a model once and reuse it throughout a batch. No automatic fallback."""

    def __init__(self, config):
        self.config = config
        self._generator = None

    def generate(self, image):
        if self.config.backend == "watershed":
            return self._watershed(image)
        if self.config.backend == "sam3":
            return self._sam3(image)
        if self._generator is None:
            self._load_sam2()
        import torch

        rgb = np.repeat(image[..., None], 3, axis=-1)
        with torch.inference_mode():
            result = self._generator.generate(rgb)
        return _filter_candidates([_rle_indices(mask["segmentation"]) for mask in result],
                                  self.config)

    def _load_sam2(self):
        try:
            import torch
            from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
            from sam2.build_sam import build_sam2
        except ImportError as exc:
            raise RuntimeError(
                "SAM 2 is not installed. Follow the SAM setup in README.md, or explicitly "
                "select --backend watershed for a model-free run."
            ) from exc
        cfg = self.config
        if cfg.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is not available")
        if cfg.device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS was requested but is not available")
        names = {"tiny": "t", "small": "s", "base_plus": "b+", "large": "l"}
        if not cfg.checkpoint or not Path(cfg.checkpoint).is_file():
            raise ValueError("SAM 2 requires a local --checkpoint; download it with the setup script")
        model = build_sam2(f"configs/sam2.1/sam2.1_hiera_{names[cfg.sam2_model]}.yaml",
                           str(Path(cfg.checkpoint).resolve()), device=cfg.device,
                           apply_postprocessing=False)
        class CompactMaskGenerator(SAM2AutomaticMaskGenerator):
            def _process_batch(self, *args, **kwargs):
                batch = super()._process_batch(*args, **kwargs)
                # Upstream retains these 256x256 logits for every candidate,
                # but refinement is finished within _process_batch and the
                # subsequent NMS/output steps never use them. Keeping them
                # makes memory grow with prompt density and can spill VRAM.
                del batch["low_res_masks"]
                return batch

        self._generator = CompactMaskGenerator(
            model, points_per_side=cfg.points_per_side, points_per_batch=cfg.points_per_batch,
            pred_iou_thresh=cfg.score_threshold, stability_score_thresh=cfg.stability_threshold,
            output_mode="uncompressed_rle", min_mask_region_area=0,
        )

    def _sam3(self, image):
        try:
            import torch
            from PIL import Image
            from sam3.model.sam3_image_processor import Sam3Processor
            from sam3.model_builder import build_sam3_image_model
        except ImportError as exc:
            raise RuntimeError("SAM 3 requires a separate Python 3.12+ / CUDA environment; "
                               "follow Meta's official SAM 3 installation instructions") from exc
        cfg = self.config
        if cfg.device != "cuda" or not torch.cuda.is_available():
            raise RuntimeError("The SAM 3 backend requires --device cuda")
        if not cfg.checkpoint or not Path(cfg.checkpoint).is_file():
            raise ValueError("SAM 3 requires a local checkpoint downloaded with authorized HF access")
        if self._generator is None:
            model = build_sam3_image_model(checkpoint_path=str(Path(cfg.checkpoint).resolve()),
                                           device=cfg.device, load_from_HF=False)
            self._generator = Sam3Processor(model, device=cfg.device,
                                            confidence_threshold=cfg.score_threshold)
        with torch.inference_mode():
            state = self._generator.set_image(Image.fromarray(image).convert("RGB"))
            output = self._generator.set_text_prompt(state=state, prompt=cfg.sam3_prompt)
            masks = output["masks"].detach().cpu().numpy()
        return _filter_candidates([np.flatnonzero(mask.reshape(image.shape)) for mask in masks], cfg)

    def _watershed(self, image):
        cfg = self.config
        if image.min() == image.max():
            return []
        smoothed = ndi.gaussian_filter(image.astype(float), cfg.watershed_sigma)
        foreground = smoothed > filters.threshold_otsu(smoothed)
        foreground = morphology.remove_small_objects(foreground, min_size=cfg.min_nucleus_area)
        foreground = ndi.binary_fill_holes(foreground)
        distance = ndi.distance_transform_edt(foreground)
        peaks = feature.peak_local_max(distance, min_distance=cfg.watershed_min_distance,
                                       labels=foreground, exclude_border=False)
        markers = np.zeros(image.shape, dtype=np.int32)
        if not len(peaks):
            return []
        markers[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
        labels = segmentation.watershed(-distance, markers, mask=foreground)
        return _filter_candidates([np.flatnonzero(labels.ravel() == label)
                                   for label in range(1, labels.max() + 1)], cfg)


def validate_candidates(candidates, shape):
    if len(shape) != 2 or any(not isinstance(n, (int, np.integer)) or n <= 0 for n in shape):
        raise ValueError("Masks must have a positive two-dimensional image shape")
    result = []
    for candidate in candidates:
        idx = np.asarray(candidate)
        if idx.ndim != 1 or not np.issubdtype(idx.dtype, np.integer):
            raise ValueError("Candidate masks must contain one-dimensional integer pixel indices")
        if not idx.size:
            continue
        if idx.min() < 0 or idx.max() >= np.prod(shape):
            raise ValueError("Candidate pixel index is outside the image")
        result.append(np.unique(idx).astype(np.int64))
    return result


def save_masks(path, candidates, shape, fingerprint=""):
    offsets = np.r_[np.int64(0), np.cumsum([len(idx) for idx in candidates], dtype=np.int64)]
    indices = np.concatenate(candidates) if candidates else np.empty(0, dtype=np.int64)
    np.savez_compressed(path, shape=np.array(shape), offsets=offsets, indices=indices,
                        fingerprint=np.array(fingerprint))


def load_masks(path, shape=None):
    path = Path(path)
    if path.suffix.lower() == ".mat":
        from scipy.io import loadmat

        masks = loadmat(path, simplify_cells=True)["masks"]
        stored_shape = tuple(np.asarray(masks["ImageSize"], dtype=int))
        values = masks["PixelIdxList"]
        # simplify_cells unwraps singleton cell arrays.
        if int(masks["NumObjects"]) == 1:
            values = [np.atleast_1d(values)]
        elif int(masks["NumObjects"]) == 0:
            values = []
        candidates = []
        h, w = stored_shape
        for value in values:
            linear = np.asarray(value, dtype=np.int64).ravel() - 1
            candidates.append((linear % h) * w + linear // h)
    else:
        with np.load(path, allow_pickle=False) as data:
            stored_shape = tuple(data["shape"].astype(int))
            indices, offsets = data["indices"], data["offsets"]
            if (not np.issubdtype(offsets.dtype, np.integer)
                    or offsets.ndim != 1 or len(offsets) == 0 or offsets[0] != 0
                    or offsets[-1] != len(indices) or np.any(np.diff(offsets) < 0)):
                raise ValueError("Invalid mask offsets")
            candidates = [indices[a:b].copy() for a, b in zip(offsets[:-1], offsets[1:])]
    if shape is not None and tuple(shape) != stored_shape:
        raise ValueError(f"Mask shape {stored_shape} does not match image shape {shape}")
    return validate_candidates(candidates, stored_shape)


@lru_cache(maxsize=8)
def _hash_file_version(path, size, modified):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _hash_file_version(str(path), stat.st_size, stat.st_mtime_ns)


def cache_fingerprint(image, config):
    fields = ("backend", "min_nucleus_area", "max_nucleus_area", "sam2_model", "device",
              "points_per_side", "points_per_batch", "score_threshold", "stability_threshold",
              "watershed_min_distance", "watershed_sigma", "sam3_prompt")
    settings = {name: getattr(config, name) for name in fields}
    packages = {"sam2": ("SAM-2", "torch", "torchvision"),
                "sam3": ("sam3", "torch", "torchvision"),
                "watershed": ("scikit-image", "scipy")}
    settings["libraries"] = {}
    for package in packages[config.backend]:
        try:
            installed = distribution(package)
            settings["libraries"][package] = {"version": installed.version,
                                                "source": installed.read_text("direct_url.json")}
        except PackageNotFoundError:
            settings["libraries"][package] = None
    if config.checkpoint and config.backend.startswith("sam"):
        settings["checkpoint_sha256"] = file_sha256(config.checkpoint)
    digest = hashlib.sha256(image.tobytes())
    digest.update(str(image.shape).encode())
    digest.update(json.dumps(settings, sort_keys=True).encode())
    # Bump when segmentation behavior changes, independent of package version.
    digest.update(b"nucleus-candidates-v1")
    return digest.hexdigest()
