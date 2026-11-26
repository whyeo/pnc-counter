"""Inference for the exported linear SVM using only NumPy (no pickle)."""

import json
from functools import lru_cache
from importlib.resources import files

import numpy as np


@lru_cache(maxsize=1)
def load_legacy_svm():
    path = files("nucleus_analysis").joinpath("data/legacy_svm.json")
    if not path.is_file():
        raise RuntimeError("Converted legacy SVM is missing from this installation")
    return json.loads(path.read_text(encoding="utf-8"))


def svm_decision(features, model=None):
    model = model or load_legacy_svm()
    x = (np.asarray(features, dtype=float) - model["mean"]) / model["std"]
    if len(model["internal_mean"]):
        x = (x - model["internal_mean"]) / model["internal_std"]
    return x @ np.asarray(model["beta"]).ravel() + model["bias"]


def is_bad_mask(row):
    model = load_legacy_svm()
    score = float(svm_decision([row[name] for name in model["features"]], model))
    return bool(model["classes"][int(score > 0)] == 1)
