"""Verified reference sets and held-out, one-to-one model evaluations."""

import argparse
import csv
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from .evaluation import compare_labels
from .review import ReviewSession
from .segmentation import file_sha256


def image_digest(directory):
    digest = hashlib.sha256()
    with np.load(Path(directory) / "images.npz", allow_pickle=False) as data:
        for name in ("ch1", "ch1_max", "ch2"):
            image = data[name]
            digest.update(str((name, image.shape, image.dtype.str)).encode())
            digest.update(image.tobytes())
    return digest.hexdigest()


def projection_digest(projections):
    digest = hashlib.sha256()
    for name, image in (("ch1", projections.dapi_mean), ("ch1_max", projections.dapi_max), ("ch2", projections.pnc_max)):
        digest.update(str((name, image.shape, image.dtype.str)).encode())
        digest.update(image.tobytes())
    return digest.hexdigest()


@contextmanager
def _reference_lock(directory):
    lock = directory / ".reference.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("Reference set is being updated; retry after the other save finishes") from exc
    try:
        handle.close()
        yield
    finally:
        lock.unlink()


def _check_verified(session):
    if not session.reviewer.strip():
        raise ValueError("Enter a reviewer name before creating a reference")
    if any(mask.flagged or not mask.reviewed for mask in session.masks.values()):
        raise ValueError("Confirm every detection and resolve follow-up flags before creating a reference")
    if not session.masks and not session.empty_reviewed:
        raise ValueError("Explicitly confirm the empty field before creating a reference")


def add_reference(session, directory, *, split, group):
    _check_verified(session)
    if split not in ("validation", "test") or not group.strip():
        raise ValueError("Choose validation/test and provide a specimen/acquisition group")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with _reference_lock(directory):
        return _add_reference(session, directory, split, group)


def _add_reference(session, directory, split, group):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "schema_version": 1, "cases": []}
    for case in manifest["cases"]:
        if case["group"] == group.strip() and case["split"] != split:
            raise ValueError("A specimen/acquisition group cannot appear in both validation and test splits")
    identity = projection_digest(session.projections)
    if any(case["image_sha256"] == identity for case in manifest["cases"]):
        raise ValueError("This image is already registered; use a new reference-set version to revise its annotation")
    revision, _ = session.save(directory / "reviews")
    case = {"id": identity[:16], "image_sha256": identity, "split": split, "group": group.strip(),
            "reviewer": session.reviewer, "review_directory": revision.relative_to(directory).as_posix(),
            "review_sha256": file_sha256(revision / "review.json")}
    manifest["cases"].append(case)
    temporary = directory / ".manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest_path


def _measurements(directory):
    with (Path(directory) / "nuclei.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    calls = {int(row["MaskID"]): bool(int(row["Positive"])) for row in rows if not int(row["BadMask"])}
    with np.load(Path(directory) / "images.npz", allow_pickle=False) as images:
        actual = set(np.unique(images["mask_overall"])) - {0}
        positive = set(np.unique(images["mask_positive"])) - {0}
    if actual != set(calls) or positive != {i for i, call in calls.items() if call}:
        raise ValueError("Prediction measurements and label images disagree")
    return calls


def benchmark(manifest_path, predictions, *, split="test", iou_threshold=0.5):
    manifest_path, predictions = Path(manifest_path).resolve(), Path(predictions).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or split not in ("validation", "test"):
        raise ValueError("Unsupported reference manifest or split")
    groups = {}
    identities = set()
    for case in manifest["cases"]:
        if case["image_sha256"] in identities:
            raise ValueError("Duplicate reference image")
        identities.add(case["image_sha256"])
        if case["group"] in groups and groups[case["group"]] != case["split"]:
            raise ValueError("Validation/test group leakage in reference manifest")
        groups[case["group"]] = case["split"]
    selected = [case for case in manifest["cases"] if case["split"] == split]
    if not selected:
        raise ValueError(f"No {split} cases in this reference set")
    candidates = [predictions / "analysis.json"] if (predictions / "analysis.json").is_file() else sorted(predictions.rglob("analysis.json"))
    runs = {}
    wanted = {case["image_sha256"] for case in selected}
    for path in candidates:
        if (path.parent / "review.json").exists():
            continue
        identity = image_digest(path.parent)
        if identity not in wanted:
            continue
        if identity in runs:
            raise ValueError("Multiple predictions for one reference image; select a single model run")
        runs[identity] = path.parent
    records = []
    for case in selected:
        reference = (manifest_path.parent / case["review_directory"].replace("\\", "/")).resolve()
        if file_sha256(reference / "review.json") != case["review_sha256"]:
            raise ValueError("Reference review changed after registration")
        session = ReviewSession.open(reference)
        _check_verified(session)
        if image_digest(reference) != case["image_sha256"]:
            raise ValueError("Reference image identity mismatch")
        predicted = runs.get(case["image_sha256"])
        if predicted is None:
            raise ValueError(f"Missing prediction for reference {case['id']}")
        with np.load(reference / "images.npz", allow_pickle=False) as r, np.load(predicted / "images.npz", allow_pickle=False) as p:
            metrics = compare_labels(r["mask_overall"], p["mask_overall"], iou_threshold, return_pairs=True)
        predicted_meta = json.loads((predicted / "analysis.json").read_text(encoding="utf-8"))
        for setting in ("border_policy", "border_margin"):
            if predicted_meta["config"].get(setting, "include" if setting == "border_policy" else 0) != getattr(session.config, setting):
                raise ValueError("Prediction and reference border rules differ; evaluate the same inclusion protocol")
        _, details = session.counts()
        truth = {i: row["positive"] for i, row in details.items() if not row["rejected"]}
        calls = _measurements(predicted)
        tp = sum(truth[pair["reference_id"]] and calls[pair["predicted_id"]] for pair in metrics["pairs"])
        n_truth_positive, n_pred_positive = sum(truth.values()), sum(calls.values())
        record = {"id": case["id"], "group": case["group"], "instances": metrics,
                  "pnc_tp": tp, "pnc_fp": n_pred_positive - tp, "pnc_fn": n_truth_positive - tp,
                  "nucleus_count_error": len(calls) - len(truth),
                  "positive_count_error": n_pred_positive - n_truth_positive,
                  "percentage_error_pp": 100 * n_pred_positive / len(calls) - 100 * n_truth_positive / len(truth)
                  if truth and calls else None,
                  "prediction": str(predicted), "prediction_config": predicted_meta["config"],
                  "prediction_analysis_sha256": file_sha256(predicted / "analysis.json"),
                  "prediction_images_sha256": file_sha256(predicted / "images.npz"),
                  "prediction_measurements_sha256": file_sha256(predicted / "nuclei.csv")}
        records.append(record)
    matched = sum(row["instances"]["matched"] for row in records)
    n_reference = sum(row["instances"]["n_reference"] for row in records)
    n_predicted = sum(row["instances"]["n_predicted"] for row in records)
    tp, fp, fn = (sum(row[key] for row in records) for key in ("pnc_tp", "pnc_fp", "pnc_fn"))
    errors = [abs(row["percentage_error_pp"]) for row in records if row["percentage_error_pp"] is not None]
    return {"split": split, "reference_manifest_sha256": file_sha256(manifest_path),
            "n_images": len(records), "instance_precision": matched / n_predicted if n_predicted else None,
            "instance_recall": matched / n_reference if n_reference else None,
            "instance_f1": 2 * matched / (n_reference + n_predicted) if n_reference + n_predicted else None,
            "mean_matched_iou": sum((row["instances"]["mean_matched_iou"] or 0)
                 * row["instances"]["matched"] for row in records) / matched if matched else None,
            "pnc_precision": tp / (tp + fp) if tp + fp else None,
            "pnc_recall": tp / (tp + fn) if tp + fn else None,
            "pnc_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "nucleus_count_mae": float(np.mean([abs(row["nucleus_count_error"]) for row in records])),
            "positive_count_mae": float(np.mean([abs(row["positive_count_error"]) for row in records])),
            "percentage_mae_pp": float(np.mean(errors)) if errors else None, "cases": records}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate predictions against a verified, group-separated reference set")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--split", choices=["validation", "test"], default="test")
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = benchmark(args.manifest, args.predictions, split=args.split, iou_threshold=args.iou)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
