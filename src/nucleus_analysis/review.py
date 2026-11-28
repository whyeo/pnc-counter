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

from .adaptive_pnc import prepare_adaptive, select_adaptive
from .config import AnalysisConfig
from .imaging import Projections
from .local_enrichment import prepare_local_enrichment, select_local_enrichment
from .output import export_result, write_csv
from .phenotype import (
    assign_spots,
    detect_spots,
    marker_image,
    pixel_size,
    segmentation_config,
    touches_border,
)
from .pipeline import analyze, threshold_pnc
from .pnc_evidence import selected_evidence
from .prominence_pnc import prepare_prominence, select_prominence
from .segmentation import file_sha256, load_masks, save_masks, validate_candidates


@dataclass(frozen=True)
class ReviewMask:
    pixels: np.ndarray
    rejected: bool = False
    flagged: bool = False
    edited: bool = False
    sources: tuple[int, ...] = ()
    reviewed: bool = False
    note: str = ""
    reviewer: str = ""
    pnc_override: bool | None = None


_UNSET = object()


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
            rejected = (bool(int(row["BadMask"])) and not bool(int(row.get("ExcludedByBorder", 0)))) or bool(int(row.get("RejectedByQuality", 0)))
            self.masks[identifier] = ReviewMask(idx, rejected,
                                                sources=(identifier,))
        self.original_masks = dict(self.masks)
        self.original_config = config
        self.next_id = max(self.masks, default=0) + 1
        self.history = []
        self.reviewer = ""
        self.empty_reviewed = False
        self._shape_features = {int(row["MaskID"]): row for row in rows}
        self._undo = []
        self._redo = []
        self._saved_state = self._signature()
        self.warning = ""
        self._marker_config = None
        self._adaptive_features = None
        self._adaptive_geometry_key = None
        self._adaptive_source_masks = ()
        self._update_marker()

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, value):
        if hasattr(self, "_config") and self._config != value and hasattr(self, "masks"):
            # Verification belongs to the recorded measurement/inclusion rules.
            self.masks = {i: replace(mask, reviewed=False) for i, mask in self.masks.items()}
            self.empty_reviewed = False
        self._config = value

    @property
    def shape(self):
        return self.projections.dapi_max.shape

    @property
    def dirty(self):
        return self._signature() != self._saved_state

    def _signature(self):
        digest = hashlib.sha256(json.dumps(self.config.to_dict(), sort_keys=True).encode())
        digest.update(json.dumps(self.projections.metadata.get("pnc_evidence"), sort_keys=True).encode())
        digest.update(self.reviewer.encode())
        digest.update(str(self.empty_reviewed).encode())
        for identifier, mask in sorted(self.masks.items()):
            digest.update(str((identifier, mask.rejected, mask.flagged, mask.edited, mask.sources,
                               mask.reviewed, mask.note, mask.reviewer, mask.pnc_override)).encode())
            digest.update(mask.pixels.tobytes())
        return digest.hexdigest()

    @classmethod
    def open(cls, directory):
        directory = Path(directory).resolve()
        metadata = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
        config = AnalysisConfig.from_dict(metadata["config"])
        with np.load(directory / "images.npz", allow_pickle=False) as data:
            projections = Projections(data["ch1"].copy(), data["ch1_max"].copy(),
                                      data["ch2"].copy(), metadata.get("input", {}),
                                      {k[6:]: data[k].copy() for k in data.files if k.startswith("pnc_z_")})
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
            if document.get("schema_version") not in (1, 2):
                raise ValueError("Unsupported review document version")
            if file_sha256(candidates_path) != document["masks_sha256"]:
                raise ValueError("Reviewed mask file checksum mismatch")
            if file_sha256(directory / "images.npz") != document["images_sha256"]:
                raise ValueError("Reviewed projections checksum mismatch")
            if document.get("nuclei_csv_sha256") and file_sha256(directory / "nuclei.csv") != document["nuclei_csv_sha256"]:
                raise ValueError("Reviewed measurements checksum mismatch")
            for identifier, mask in list(session.masks.items()):
                state = document["states"][str(identifier)]
                session.masks[identifier] = replace(mask, rejected=state["rejected"], flagged=state["flagged"],
                    edited=state["edited"], sources=tuple(state["sources"]),
                    reviewed=state.get("reviewed", False), note=state.get("note", ""),
                    reviewer=state.get("reviewer", ""), pnc_override=state.get("pnc_override"))
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
                    idx, state["rejected"], state["flagged"], state["edited"], tuple(state["sources"]),
                    state.get("reviewed", False), state.get("note", ""), state.get("reviewer", ""),
                    state.get("pnc_override"))
            session.original_config = AnalysisConfig.from_dict(document["original_config"])
            session.original_directory = Path(document["original_directory"]) if document["original_directory"] else None
            session.history = document["history"]
            session.reviewer = document.get("reviewer", "")
            session.empty_reviewed = document.get("empty_reviewed", False)
            session.next_id = max(document["next_id"], max(session.masks, default=0) + 1)
            session.warning = document.get("warning", "")
            session._saved_state = session._signature()
        return session

    def _record(self, operation, ids, detail=""):
        self.history.append({"time_utc": datetime.now(timezone.utc).isoformat(),
                             "operation": operation, "mask_ids": [int(i) for i in ids], "detail": detail,
                             "reviewer": self.reviewer})

    def _commit(self, operation, masks, ids, detail="", config=None, empty_reviewed=False):
        self._undo.append((dict(self.masks), self.config, self.empty_reviewed))
        self._redo.clear()
        self.masks = masks
        self.config = config or self.config
        self.empty_reviewed = empty_reviewed
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
        masks[identifier] = replace(old, pixels=pixels, edited=True, reviewed=False, pnc_override=None)
        self._commit("redraw", masks, [identifier])

    def mark(self, identifiers, *, rejected=None, flagged=None, reviewed=None, note=None, pnc_override=_UNSET):
        identifiers = list(identifiers)
        if not identifiers:
            if reviewed is True and not self.masks:
                self._commit("confirm_empty_field", {}, [], empty_reviewed=True)
                return
            raise ValueError("Select a nucleus first")
        changes = {k: v for k, v in (("rejected", rejected), ("flagged", flagged)) if v is not None}
        if rejected is not None or flagged is True:
            changes["reviewed"] = False
        if reviewed is not None:
            changes.update(reviewed=reviewed, reviewer=self.reviewer)
        if note is not None:
            changes["note"] = str(note)
        if pnc_override is not _UNSET:
            if pnc_override is not None and not isinstance(pnc_override, bool):
                raise ValueError("PNC override must be True, False, or None (automatic)")
            changes.update(pnc_override=pnc_override, reviewed=False)
        masks = dict(self.masks)
        for identifier in identifiers:
            masks[identifier] = replace(masks[identifier], **changes)
            if reviewed is True and masks[identifier].flagged:
                raise ValueError("Resolve the follow-up flag before confirming this nucleus")
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
        masks[identifier] = replace(old, pixels=outside, edited=True, reviewed=False, pnc_override=None)
        masks[new_id] = replace(old, pixels=inside, edited=True, reviewed=False, pnc_override=None)
        self._commit("split", masks, [identifier, new_id])
        return identifier, new_id

    def undo(self):
        if not self._undo:
            return False
        self._redo.append((dict(self.masks), self.config, self.empty_reviewed))
        self.masks, self.config, self.empty_reviewed = self._undo.pop()
        self._record("undo", [])
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append((dict(self.masks), self.config, self.empty_reviewed))
        self.masks, self.config, self.empty_reviewed = self._redo.pop()
        self._record("redo", [])
        return True

    def reset(self):
        self._commit("reset_to_original", dict(self.original_masks), self.original_masks,
                     config=self.original_config)

    def set_pnc_config(self, config, preview=None):
        if config != self.config:
            self._commit("change_pnc_settings", dict(self.masks), [],
                         json.dumps({"pnc_mode": config.pnc_mode, "pnc_sensitivity": config.pnc_sensitivity,
                                     "pnc_enrichment_threshold": config.pnc_enrichment_threshold}),
                         config=config)
        if preview is not None:
            for name in ("_marker_config", "_positive_pixels", "_spot_labels", "_spot_rows",
                         "_adaptive_features", "_adaptive_geometry_key", "_adaptive_source_masks"):
                setattr(self, name, getattr(preview, name))

    def _update_marker(self):
        geometry = None
        if self.config.pnc_mode in ("adaptive", "prominence", "enrichment"):
            calibration = pixel_size(self.config, self.projections.metadata)
            active = [(i, mask.pixels) for i, mask in self.masks.items() if not mask.rejected
                      and not (self.config.border_policy == "exclude"
                               and touches_border(mask.pixels, self.shape, self.config.border_margin))]
            geometry = (tuple((i, id(pixels)) for i, pixels in active), calibration, self.config.spot_min_distance,
                        self.config.pnc_mode, self.config.pnc_z_policy, id(self.projections))
            if self._adaptive_geometry_key != geometry:
                prepare = (prepare_local_enrichment if self.config.pnc_mode == "enrichment" else
                           prepare_prominence if self.config.pnc_mode == "prominence" else prepare_adaptive)
                options = {"evidence": selected_evidence(self.projections, self.config), "z_policy": self.config.pnc_z_policy} if self.config.pnc_mode == "prominence" else {}
                self._adaptive_features = prepare(self.projections.pnc_max,
                    [p for _, p in active], [i for i, _ in active], calibration, self.config.spot_min_distance, **options)
                self._adaptive_geometry_key = geometry
                # Retain immutable source arrays so their identities cannot be
                # recycled while this cache key is active.
                self._adaptive_source_masks = tuple(p for _, p in active)
        marker_key = (self.config, geometry)
        if self._marker_config == marker_key:
            return
        if self.config.pnc_mode in ("adaptive", "prominence", "enrichment"):
            select = select_prominence if self.config.pnc_mode == "prominence" else select_adaptive
            if self.config.pnc_mode == "enrichment":
                self._positive_pixels, self._spot_labels, self._spot_rows = select_local_enrichment(
                    self._adaptive_features, self.config.pnc_enrichment_threshold)
            else:
                self._positive_pixels, self._spot_labels, self._spot_rows = select(
                    self._adaptive_features, self.config.pnc_sensitivity, self.config.spot_min_area, self.config.spot_max_area)
        else:
            self._positive_pixels = threshold_pnc(marker_image(self.projections.pnc_max, self.config), self.config)
            self._spot_labels, self._spot_rows = detect_spots(self._positive_pixels, self.config)
        self._marker_config = marker_key

    def counts(self):
        self._update_marker()
        positive = negative = rejected = 0
        details = {}
        rows = []
        for identifier, mask in self.masks.items():
            border = touches_border(mask.pixels, self.shape, self.config.border_margin)
            rows.append({"MaskID": identifier, "Area": len(mask.pixels),
                         "BadMask": mask.rejected or (border and self.config.border_policy == "exclude"),
                         "TouchesBorder": border})
        spot_counts = assign_spots(rows, [self.masks[r["MaskID"]].pixels for r in rows], self._spot_rows)
        status = {row["MaskID"]: row for row in rows}
        for identifier, mask in self.masks.items():
            pixels = int(self._positive_pixels.ravel()[mask.pixels].sum())
            excluded = status[identifier]["BadMask"]
            call = (spot_counts[identifier] >= (1 if self.config.pnc_mode == "enrichment" else self.config.min_spot_count) if self.config.pnc_mode in ("spots", "adaptive", "prominence", "enrichment")
                    else pixels >= self.config.positive_threshold)
            if mask.pnc_override is not None:
                call = mask.pnc_override
            is_positive = not excluded and call
            details[identifier] = {"positive_pixels": pixels, "positive": is_positive,
                                   "spots": spot_counts[identifier], "rejected": bool(excluded),
                                   "border": status[identifier]["TouchesBorder"]}
            if self.config.pnc_mode in ("adaptive", "prominence", "enrichment"):
                details[identifier]["signal_score"] = self._adaptive_features.measurements.get(identifier, {}).get("max_score", 0.)
                details[identifier]["candidate_flags"] = sorted({flag for row in self._adaptive_features.candidates
                    if row["NucleusID"] == identifier for flag in row.get("ReviewFlags", "").split("; ") if flag})
            if self.config.pnc_mode == "enrichment":
                measurement = self._adaptive_features.measurements.get(identifier, {})
                details[identifier]["enrichment"] = measurement.get("max_score", 0.)
                details[identifier]["measurement_status"] = measurement.get("status", "unsupported")
                details[identifier]["candidate_flags"] = [f for f in measurement.get("flags", "").split("; ") if f]
            rejected += excluded
            positive += is_positive
            negative += not excluded and not is_positive
        total = positive + negative
        return {"percentage": 100 * positive / total if total else None,
                "n_positive": positive, "n_negative": negative, "n_bad": rejected,
                "n_total": total, "n_masks": len(self.masks),
                "n_flagged": sum(mask.flagged for mask in self.masks.values())}, details

    def review_queue(self, category="unreviewed"):
        if category not in ("all", "unreviewed", "flagged", "uncertain", "rejected"):
            raise ValueError("Unknown review queue category")
        _, details = self.counts()
        effective = segmentation_config(self.config, self.projections.metadata)
        queue = []
        for identifier, mask in self.masks.items():
            reasons = []
            priority = 0
            if mask.flagged:
                reasons.append("flagged for follow-up")
                priority += 100
            for reason in details[identifier].get("candidate_flags", []):
                reasons.append(reason)
                priority += 5
            if details[identifier]["border"]:
                reasons.append("partial/border nucleus")
                priority += 40
            spot_mode = self.config.pnc_mode in ("spots", "adaptive", "prominence", "enrichment")
            if self.config.pnc_mode == "enrichment":
                value = details[identifier]["enrichment"]
                cutoff = self.config.pnc_enrichment_threshold
                margin = max(.05, .1 * cutoff)
            else:
                value = details[identifier]["spots"] if spot_mode else details[identifier]["positive_pixels"]
                cutoff = self.config.min_spot_count if spot_mode else self.config.positive_threshold
                margin = 0 if spot_mode else self.config.review_positive_margin
            if abs(value - cutoff) <= margin:
                reasons.append("PNC measurement near cutoff")
                priority += 30
            if not effective.min_nucleus_area <= len(mask.pixels) <= effective.max_nucleus_area:
                reasons.append("outside automatic area range")
                priority += 20
            features = self._shape_features.get(identifier, {})
            if not mask.edited and (float(features.get("Solidity", 1)) < 0.9
                                    or float(features.get("Eccentricity", 0)) > 0.95):
                reasons.append("irregular/elongated shape")
                priority += 20
            if details[identifier]["rejected"]:
                reasons.append("excluded detection")
                priority += 10
            uncertain = priority > 0 and not mask.reviewed
            include = (category == "all" or category == "unreviewed" and not mask.reviewed
                       or category == "flagged" and mask.flagged or category == "uncertain" and uncertain
                       or category == "rejected" and details[identifier]["rejected"])
            if include:
                queue.append({"MaskID": identifier, "priority": priority if not mask.reviewed else 0,
                              "reasons": reasons, "reviewed": mask.reviewed})
        return sorted(queue, key=lambda row: (-row["priority"], row["MaskID"]))

    def result(self):
        identifiers = sorted(self.masks)
        result = analyze(self.projections, self.config, masks=[self.masks[i].pixels for i in identifiers],
                         mask_ids=identifiers, rejected_ids={i for i in identifiers if self.masks[i].rejected},
                         suppress_overlaps=False, positive_overrides={i: self.masks[i].pnc_override
                             for i in identifiers if self.masks[i].pnc_override is not None})
        for row in result.full_stats:
            mask = self.masks[row["MaskID"]]
            row.update(ReviewFlag=int(mask.flagged), ManuallyEdited=int(mask.edited),
                       SourceMaskIDs=";".join(map(str, mask.sources)), Reviewed=int(mask.reviewed),
                       ReviewNote=mask.note, Reviewer=mask.reviewer,
                       PNCOverride="auto" if mask.pnc_override is None else int(mask.pnc_override))
        result.basic_stats["n_flagged"] = sum(m.flagged for m in self.masks.values())
        return result

    @staticmethod
    def _state(identifier, mask):
        return {"id": int(identifier), "rejected": bool(mask.rejected), "flagged": bool(mask.flagged),
                "edited": bool(mask.edited), "sources": list(mask.sources), "reviewed": mask.reviewed,
                "note": mask.note, "reviewer": mask.reviewer, "pnc_override": mask.pnc_override}

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
        labels[:] = result.images["mask_overall"]
        tifffile.imwrite(temporary / "reviewed_labels.tif", labels, metadata={"axes": "YX"})
        document = {"schema_version": 2, "original_directory": str(self.original_directory)
                    if self.original_directory else None, "original_config": self.original_config.to_dict(),
                    "states": {str(i): self._state(i, mask) for i, mask in sorted(self.masks.items())},
                    "original_states": [self._state(i, self.original_masks[i]) for i in original_ids],
                    "history": self.history, "next_id": self.next_id, "warning": self.warning,
                    "reviewer": self.reviewer,
                    "empty_reviewed": self.empty_reviewed,
                    "masks_sha256": file_sha256(temporary / "nuclei_masks.npz"),
                    "original_masks_sha256": file_sha256(temporary / "original_masks.npz"),
                    "images_sha256": file_sha256(temporary / "images.npz")}
        document["nuclei_csv_sha256"] = file_sha256(temporary / "nuclei.csv")
        (temporary / "review.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        write_csv(temporary / "summary.csv", [result.basic_stats], list(result.basic_stats))
        temporary.rename(destination)
        self._saved_state = self._signature()
        return destination, result.basic_stats
