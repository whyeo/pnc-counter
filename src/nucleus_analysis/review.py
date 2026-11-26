"""Manual correction model independent of Tk, SAM, and the original raw images."""

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage as ndi
from skimage.draw import polygon

from .config import AnalysisConfig
from .imaging import Projections
from .output import export_result, write_csv
from .pipeline import analyze, threshold_pnc
from .segmentation import file_sha256, load_masks, save_masks, validate_candidates


@dataclass(frozen=True)
class ReviewMask:
    pixels: np.ndarray
    rejected: bool = False
    flagged: bool = False
    edited: bool = False
    sources: tuple[int, ...] = ()


class ReviewSession:
    """Stable nucleus IDs, reversible edits, and immutable saved revisions.

    Sparse masks are shared between undo snapshots, never changed in-place.
    Explicit reviewer decisions override the automatic SVM and overlap filters.
    """

    def __init__(self, projections, config, masks, rows, *, original_directory=None):
        if len(masks) != len(rows):
            raise ValueError("Mask and measurement row counts differ")
        masks = validate_candidates(masks, projections.dapi_max.shape)
        if len(masks) != len(rows):
            raise ValueError("Review masks must be nonempty")
        self.projections = projections
        self.config = config
        self.original_directory = Path(original_directory).resolve() if original_directory else None
        self.masks = {}
        for idx, row in zip(masks, rows):
            identifier = int(row["MaskID"])
            if identifier <= 0 or identifier > np.iinfo(np.uint32).max or identifier in self.masks:
                raise ValueError("Review mask IDs must be unique positive uint32 integers")
            idx.flags.writeable = False
            self.masks[identifier] = ReviewMask(idx, bool(int(row["BadMask"])), sources=(identifier,))
        self.original_masks = dict(self.masks)
        self.original_config = config
        self.next_id = max(self.masks, default=0) + 1
        self.history = []
        self._undo = []
        self._redo = []
        self._saved_state = self._signature()
        self.warning = ""
        self._positive_pixels = threshold_pnc(projections.pnc_max, config)

    @property
    def shape(self):
        return self.projections.dapi_max.shape

    @property
    def dirty(self):
        return self._signature() != self._saved_state

    def _signature(self):
        digest = hashlib.sha256(json.dumps(self.config.to_dict(), sort_keys=True).encode())
        for identifier, mask in sorted(self.masks.items()):
            digest.update(str((identifier, mask.rejected, mask.flagged, mask.edited, mask.sources)).encode())
            digest.update(mask.pixels.tobytes())
        return digest.hexdigest()

    @classmethod
    def open(cls, directory):
        directory = Path(directory).resolve()
        metadata = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
        config = AnalysisConfig(**metadata["config"])
        with np.load(directory / "images.npz", allow_pickle=False) as data:
            projections = Projections(data["ch1"].copy(), data["ch1_max"].copy(),
                                      data["ch2"].copy(), metadata.get("input", {}))
            fallback_labels = {key: data[key].copy() for key in ("mask_overall", "mask_bad")}
        with (directory / "nuclei.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        candidates_path = directory / "nuclei_masks.npz"
        recovered = False
        if candidates_path.is_file():
            candidates = load_masks(candidates_path, projections.dapi_max.shape)
        else:
            # Old exports lack exact candidate masks. Recover them from their
            # recorded cache/import if available, without loading a model.
            provenance = metadata.get("segmentation", {})
            source = provenance.get("cache") or provenance.get("path")
            candidates = None
            if source and Path(source).is_file():
                replay = analyze(projections, config, masks=load_masks(source, projections.dapi_max.shape))
                matches = len(replay.full_stats) == len(rows) and all(
                    a["MaskID"] == int(b["MaskID"]) and a["Area"] == int(b["Area"])
                    and a["NumberCh2PixelsPositive"] == int(b["NumberCh2PixelsPositive"])
                    and abs(a["CentroidX"] - float(b["CentroidX"])) < 1e-6
                    and abs(a["CentroidY"] - float(b["CentroidY"])) < 1e-6
                    for a, b in zip(replay.full_stats, rows))
                if matches:
                    candidates = replay.masks
            if candidates is None:
                candidates = [np.flatnonzero(fallback_labels[
                    "mask_bad" if int(row["BadMask"]) else "mask_overall"].ravel() == int(row["MaskID"]))
                    for row in rows]
                recovered = True
        session = cls(projections, config, candidates, rows, original_directory=directory)
        if recovered:
            session.warning = ("Legacy export recovered from label images; original overlaps may be "
                               "trimmed. Re-export from the candidate cache for exact boundaries.")
        review_path = directory / "review.json"
        if review_path.is_file():
            document = json.loads(review_path.read_text(encoding="utf-8"))
            if document.get("schema_version") != 1:
                raise ValueError("Unsupported review document version")
            if file_sha256(candidates_path) != document["masks_sha256"]:
                raise ValueError("Reviewed mask file checksum mismatch")
            if file_sha256(directory / "images.npz") != document["images_sha256"]:
                raise ValueError("Reviewed projections checksum mismatch")
            for identifier, mask in list(session.masks.items()):
                state = document["states"][str(identifier)]
                session.masks[identifier] = replace(mask, rejected=state["rejected"], flagged=state["flagged"],
                                                     edited=state["edited"], sources=tuple(state["sources"]))
            original = load_masks(directory / "original_masks.npz", session.shape)
            if file_sha256(directory / "original_masks.npz") != document["original_masks_sha256"]:
                raise ValueError("Original mask snapshot checksum mismatch")
            original_states = document["original_states"]
            if len(original) != len(original_states):
                raise ValueError("Original mask state count mismatch")
            session.original_masks = {}
            for idx, state in zip(original, original_states):
                idx.flags.writeable = False
                session.original_masks[int(state["id"])] = ReviewMask(
                    idx, state["rejected"], state["flagged"], state["edited"], tuple(state["sources"]))
            session.original_config = AnalysisConfig(**document["original_config"])
            session.original_directory = Path(document["original_directory"]) if document["original_directory"] else None
            session.history = document["history"]
            session.next_id = max(document["next_id"], max(session.masks, default=0) + 1)
            session.warning = document.get("warning", "")
            session._saved_state = session._signature()
        return session

    def _record(self, operation, ids, detail=""):
        self.history.append({"time_utc": datetime.now(timezone.utc).isoformat(),
                             "operation": operation, "mask_ids": [int(i) for i in ids], "detail": detail})

    def _commit(self, operation, masks, ids, detail="", config=None):
        self._undo.append((dict(self.masks), self.config))
        self._redo.clear()
        self.masks = masks
        self.config = config or self.config
        self._record(operation, ids, detail)

    def polygon_pixels(self, points):
        points = np.asarray(points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
            raise ValueError("Draw at least three finite outline points")
        if np.any(points < 0) or np.any(points[:, 0] > self.shape[1] - 1) or np.any(points[:, 1] > self.shape[0] - 1):
            raise ValueError("Outline points must be inside the image")
        x, y = points.T
        if abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) < 1:
            raise ValueError("Outline has no area; draw a closed boundary around a nucleus")
        rr, cc = polygon(y, x, shape=self.shape)
        idx = np.unique(np.ravel_multi_index((rr, cc), self.shape))
        if len(idx) < 3:
            raise ValueError("Outline must contain at least three pixels")
        if not self._connected(idx):
            raise ValueError("Outline must describe one connected nucleus")
        idx.flags.writeable = False
        return idx

    def _check_overlap(self, pixels, exclude=()):
        for identifier, mask in self.masks.items():
            if identifier not in exclude and np.intersect1d(pixels, mask.pixels, assume_unique=True).size:
                raise ValueError(f"Outline overlaps nucleus {identifier}. Redraw tighter, merge, or delete it first.")

    def add(self, points):
        pixels = self.polygon_pixels(points)
        self._check_overlap(pixels)
        identifier = self.next_id
        if identifier > np.iinfo(np.uint32).max:
            raise ValueError("No more nucleus IDs are available")
        self.next_id += 1
        masks = dict(self.masks)
        masks[identifier] = ReviewMask(pixels, edited=True)
        self._commit("add", masks, [identifier])
        return identifier

    def redraw(self, identifier, points):
        old = self.masks[identifier]
        pixels = self.polygon_pixels(points)
        self._check_overlap(pixels, [identifier])
        masks = dict(self.masks)
        masks[identifier] = replace(old, pixels=pixels, edited=True)
        self._commit("redraw", masks, [identifier])

    def mark(self, identifiers, *, rejected=None, flagged=None):
        identifiers = list(identifiers)
        if not identifiers:
            raise ValueError("Select a nucleus first")
        changes = {k: v for k, v in (("rejected", rejected), ("flagged", flagged)) if v is not None}
        masks = dict(self.masks)
        for identifier in identifiers:
            masks[identifier] = replace(masks[identifier], **changes)
        if rejected is False:
            for identifier in identifiers:
                if not self.masks[identifier].rejected:
                    continue
                for other, mask in masks.items():
                    if other != identifier and not mask.rejected:
                        overlap = np.intersect1d(masks[identifier].pixels, mask.pixels, assume_unique=True).size
                        if overlap > self.config.overlap_threshold * len(masks[identifier].pixels):
                            raise ValueError(f"Nucleus {identifier} overlaps accepted nucleus {other}. "
                                             "Redraw or delete the duplicate before accepting it.")
        self._commit("mark", masks, identifiers, json.dumps(changes, sort_keys=True))

    def delete(self, identifiers):
        identifiers = list(identifiers)
        if not identifiers:
            raise ValueError("Select a nucleus first")
        masks = dict(self.masks)
        for identifier in identifiers:
            del masks[identifier]
        self._commit("delete", masks, identifiers)

    def merge(self, identifiers):
        identifiers = sorted(set(identifiers))
        if len(identifiers) < 2:
            raise ValueError("Select at least two nuclei to merge (Ctrl+click)")
        originals = [self.masks[i] for i in identifiers]
        pixels = np.unique(np.concatenate([mask.pixels for mask in originals]))
        self._check_overlap(pixels, identifiers)
        pixels.flags.writeable = False
        sources = tuple(sorted({i for mask in originals for i in mask.sources}))
        masks = {i: mask for i, mask in self.masks.items() if i not in identifiers}
        masks[identifiers[0]] = ReviewMask(pixels, flagged=any(m.flagged for m in originals),
                                           edited=True, sources=sources)
        self._commit("merge", masks, identifiers)
        return identifiers[0]

    def _connected(self, pixels):
        yy, xx = np.unravel_index(pixels, self.shape)
        local = np.zeros((yy.max() - yy.min() + 1, xx.max() - xx.min() + 1), dtype=bool)
        local[yy - yy.min(), xx - xx.min()] = True
        return ndi.label(local, structure=np.ones((3, 3)))[1] == 1

    def split(self, identifier, points):
        old = self.masks[identifier]
        inside = np.intersect1d(old.pixels, self.polygon_pixels(points), assume_unique=True)
        outside = np.setdiff1d(old.pixels, inside, assume_unique=True)
        if any(len(part) < 3 or not self._connected(part) for part in (inside, outside)):
            raise ValueError("Split outline must divide the selected nucleus into two connected parts of at least 3 pixels")
        inside.flags.writeable = outside.flags.writeable = False
        new_id = self.next_id
        if new_id > np.iinfo(np.uint32).max:
            raise ValueError("No more nucleus IDs are available")
        self.next_id += 1
        masks = dict(self.masks)
        masks[identifier] = replace(old, pixels=outside, edited=True)
        masks[new_id] = replace(old, pixels=inside, edited=True)
        self._commit("split", masks, [identifier, new_id])
        return identifier, new_id

    def undo(self):
        if not self._undo:
            return False
        self._redo.append((dict(self.masks), self.config))
        self.masks, self.config = self._undo.pop()
        self._record("undo", [])
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append((dict(self.masks), self.config))
        self.masks, self.config = self._redo.pop()
        self._record("redo", [])
        return True

    def reset(self):
        self._commit("reset_to_original", dict(self.original_masks), self.original_masks,
                     config=self.original_config)

    def counts(self):
        positive = negative = rejected = 0
        details = {}
        for identifier, mask in self.masks.items():
            pixels = int(self._positive_pixels.ravel()[mask.pixels].sum())
            is_positive = not mask.rejected and pixels >= self.config.positive_threshold
            details[identifier] = {"positive_pixels": pixels, "positive": is_positive}
            rejected += mask.rejected
            positive += is_positive
            negative += not mask.rejected and not is_positive
        total = positive + negative
        return {"percentage": 100 * positive / total if total else None,
                "n_positive": positive, "n_negative": negative, "n_bad": rejected,
                "n_total": total, "n_masks": len(self.masks),
                "n_flagged": sum(mask.flagged for mask in self.masks.values())}, details

    def result(self):
        identifiers = sorted(self.masks)
        result = analyze(self.projections, self.config, masks=[self.masks[i].pixels for i in identifiers],
                         mask_ids=identifiers, rejected_ids={i for i in identifiers if self.masks[i].rejected},
                         suppress_overlaps=False)
        for row in result.full_stats:
            mask = self.masks[row["MaskID"]]
            row.update(ReviewFlag=int(mask.flagged), ManuallyEdited=int(mask.edited),
                       SourceMaskIDs=";".join(map(str, mask.sources)))
        result.basic_stats["n_flagged"] = sum(m.flagged for m in self.masks.values())
        return result

    @staticmethod
    def _state(identifier, mask):
        return {"id": int(identifier), "rejected": bool(mask.rejected), "flagged": bool(mask.flagged),
                "edited": bool(mask.edited), "sources": list(mask.sources)}

    def save(self, parent):
        """Write a new self-contained revision; never overwrite an existing result."""
        parent = Path(parent).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        destination = parent / ("review-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                                + "-" + uuid.uuid4().hex[:8])
        # All files are complete before the directory is exposed as a revision.
        temporary = parent / (".saving-" + uuid.uuid4().hex)
        temporary.mkdir()
        result = self.result()
        export_result(result, temporary, provenance={"kind": "manual_review",
                      "original_directory": str(self.original_directory) if self.original_directory else None,
                      "quality_decisions": "Reviewer acceptance/rejection overrides SVM and overlap suppression"})
        original_ids = sorted(self.original_masks)
        save_masks(temporary / "original_masks.npz",
                   [self.original_masks[i].pixels for i in original_ids], self.shape)
        labels = np.zeros(self.shape, dtype=np.uint32)
        for identifier, mask in sorted(self.masks.items()):
            if not mask.rejected:
                labels.ravel()[mask.pixels] = identifier
        tifffile.imwrite(temporary / "reviewed_labels.tif", labels, metadata={"axes": "YX"})
        document = {"schema_version": 1, "original_directory": str(self.original_directory)
                    if self.original_directory else None, "original_config": self.original_config.to_dict(),
                    "states": {str(i): self._state(i, mask) for i, mask in sorted(self.masks.items())},
                    "original_states": [self._state(i, self.original_masks[i]) for i in original_ids],
                    "history": self.history, "next_id": self.next_id, "warning": self.warning,
                    "masks_sha256": file_sha256(temporary / "nuclei_masks.npz"),
                    "original_masks_sha256": file_sha256(temporary / "original_masks.npz"),
                    "images_sha256": file_sha256(temporary / "images.npz")}
        (temporary / "review.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        write_csv(temporary / "summary.csv", [result.basic_stats], list(result.basic_stats))
        temporary.rename(destination)
        self._saved_state = self._signature()
        return destination, result.basic_stats
