"""Compare an exported run against another run or reviewed label TIFFs.

Usage: python tools/compare_segmentations.py reference/images.npz predicted/images.npz
       python tools/compare_segmentations.py reviewed_labels.tif predicted/images.npz
Legacy output is agreement evidence, never ground-truth accuracy.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import tifffile

from nucleus_analysis.evaluation import compare_labels


def read_labels(path):
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as data:
            return data["mask_overall"].copy()
    return tifffile.imread(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("predicted", type=Path)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_labels(read_labels(args.reference), read_labels(args.predicted), args.iou)
    text = json.dumps(result, indent=2) + "\n"
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
