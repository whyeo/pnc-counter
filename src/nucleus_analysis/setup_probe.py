"""Verify actual Torch kernels and a real SAM prompt in a fresh process."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--model", choices=("tiny", "small"), required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("Checking PyTorch and image-processing kernels", flush=True)
    import numpy as np
    import torch
    import torchvision
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    from .preferences import detect_hardware

    if args.device == "cpu":
        # Keep the small installation check from oversubscribing large CPUs.
        # This applies only to this disposable verification process.
        torch.set_num_threads(min(4, torch.get_num_threads()))
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("PyTorch cannot use this NVIDIA driver. Update the driver and recheck, or choose CPU setup.")
    value = torch.ones(8, device=args.device)
    assert (value * value).sum().item() == 8
    boxes = torch.tensor([[0., 0., 10., 10.]], device=args.device)
    assert torchvision.ops.nms(boxes, torch.ones(1, device=args.device), .5).numel() == 1
    suffix = "t" if args.model == "tiny" else "s"
    print("Loading the selected SAM checkpoint", flush=True)
    model = build_sam2(f"configs/sam2.1/sam2.1_hiera_{suffix}.yaml", str(args.checkpoint),
                       device=args.device, apply_postprocessing=False)
    predictor = SAM2ImagePredictor(model)
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[20:44, 20:44] = 180
    with torch.inference_mode():
        print("Running a SAM image and point prompt", flush=True)
        predictor.set_image(image)
        masks, scores, _ = predictor.predict(point_coords=np.array([[32, 32]]), point_labels=np.array([1]))
    if not masks.size or not np.isfinite(scores).all():
        raise RuntimeError("SAM did not produce valid masks during the installation check")
    hardware = detect_hardware()
    hardware["device"] = args.device
    args.output.write_text(json.dumps({"ok": True, "device": args.device, "hardware": hardware,
                                       "torch": torch.__version__, "torchvision": torchvision.__version__}), encoding="utf-8")
    print("PyTorch kernels and SAM image inference verified", flush=True)


if __name__ == "__main__":
    main()
