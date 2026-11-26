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

    def __post_init__(self):
        choices = {
            "backend": ("sam2", "sam3", "watershed"),
            "threshold_mode": ("local", "global"),
            "quality_filter": ("none", "legacy-svm"),
            "sam2_model": ("tiny", "small", "base_plus", "large"),
        }
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name} must be one of {allowed}")
        for name in ("min_nucleus_area", "max_nucleus_area", "neighborhood_size",
                     "points_per_side", "points_per_batch", "watershed_min_distance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("positive_threshold", "dapi_channel", "pnc_channel", "time_index",
                     "position_index"):
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
        if not math.isfinite(self.watershed_sigma) or self.watershed_sigma <= 0:
            raise ValueError("watershed_sigma must be positive and finite")
        if self.device not in ("cpu", "cuda", "mps"):
            raise ValueError("device must be cpu, cuda, or mps")
        if not isinstance(self.sam3_prompt, str) or not self.sam3_prompt.strip():
            raise ValueError("sam3_prompt must be nonempty text")

    def to_dict(self):
        return asdict(self)

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))
