"""Explicit, serializable analysis settings. Areas and distances are in pixels."""

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalysisConfig:
    backend: str = "sam2"
    min_nucleus_area: int = 5000
    max_nucleus_area: int = 50000
    positive_threshold: int = 10
    threshold_mode: str = "local"
    image_threshold: float = 90.0
    neighborhood_size: int = 21
    dapi_channel: int = 0
    pnc_channel: int = 1
    time_index: int = 0
    position_index: int = 0
    quality_filter: str = "none"
    overlap_threshold: float = 0.1
    sam2_model: str = "tiny"
    sam3_prompt: str = "cell nucleus"
    checkpoint: str | None = None
    device: str = "cpu"
    points_per_side: int = 32
    points_per_batch: int = 16
    score_threshold: float = 0.7
    stability_threshold: float = 0.95
    watershed_min_distance: int = 30
    watershed_sigma: float = 2.0
    min_nucleus_area_um2: float | None = None
    max_nucleus_area_um2: float | None = None
    pixel_size_x_um: float | None = None
    pixel_size_y_um: float | None = None
    border_policy: str = "include"
    border_margin: int = 0
    pnc_mode: str = "pixels"
    pnc_sensitivity: float = 50.0
    pnc_z_policy: str = "auto"
    min_spot_count: int = 1
    spot_min_area: int = 3
    spot_max_area: int = 500
    spot_min_distance: int = 3
    spot_background_sigma: float = 0.0
    review_positive_margin: int = 3

    def __post_init__(self):
        choices = {
            "backend": ("sam2", "sam3", "watershed"),
            "threshold_mode": ("local", "global"),
            "quality_filter": ("none", "legacy-svm"),
            "sam2_model": ("tiny", "small", "base_plus", "large"),
            "border_policy": ("include", "exclude"),
            "pnc_mode": ("pixels", "spots", "adaptive", "prominence"),
            "pnc_z_policy": ("auto", "projection"),
        }
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name} must be one of {allowed}")
        for name in ("min_nucleus_area", "max_nucleus_area", "neighborhood_size",
                     "points_per_side", "points_per_batch", "watershed_min_distance",
                     "min_spot_count", "spot_min_area", "spot_max_area", "spot_min_distance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("positive_threshold", "dapi_channel", "pnc_channel", "time_index",
                     "position_index", "border_margin", "review_positive_margin"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.min_nucleus_area > self.max_nucleus_area:
            raise ValueError("min_nucleus_area must not exceed max_nucleus_area")
        if self.neighborhood_size % 2 != 1 or self.neighborhood_size < 3:
            raise ValueError("neighborhood_size must be odd and at least 3")
        if self.dapi_channel == self.pnc_channel:
            raise ValueError("DAPI and PNC must use different channels")
        for name in ("overlap_threshold", "score_threshold", "stability_threshold"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not 0 <= self.image_threshold <= 100:
            raise ValueError("image_threshold must be between 0 and 100")
        if isinstance(self.pnc_sensitivity, bool) or not math.isfinite(self.pnc_sensitivity) or not 0 <= self.pnc_sensitivity <= 100:
            raise ValueError("pnc_sensitivity must be finite and between 0 and 100")
        if not math.isfinite(self.watershed_sigma) or self.watershed_sigma <= 0:
            raise ValueError("watershed_sigma must be positive and finite")
        if self.device not in ("cpu", "cuda", "mps"):
            raise ValueError("device must be cpu, cuda, or mps")
        if not isinstance(self.sam3_prompt, str) or not self.sam3_prompt.strip():
            raise ValueError("sam3_prompt must be nonempty text")
        for first, last in (("min_nucleus_area_um2", "max_nucleus_area_um2"),
                            ("pixel_size_x_um", "pixel_size_y_um")):
            a, b = getattr(self, first), getattr(self, last)
            if (a is None) != (b is None):
                raise ValueError(f"Specify both {first} and {last}")
            if a is not None and any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in (a, b)):
                raise ValueError(f"{first} and {last} must be positive and finite")
        if self.min_nucleus_area_um2 is not None and self.min_nucleus_area_um2 > self.max_nucleus_area_um2:
            raise ValueError("Minimum physical area must not exceed maximum physical area")
        if self.spot_min_area > self.spot_max_area:
            raise ValueError("spot_min_area must not exceed spot_max_area")
        if not math.isfinite(self.spot_background_sigma) or self.spot_background_sigma < 0:
            raise ValueError("spot_background_sigma must be nonnegative and finite")

    def to_dict(self):
        return asdict(self)

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))
