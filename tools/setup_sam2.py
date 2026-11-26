"""Install official SAM 2.1 and/or download a checkpoint to a local directory.

Run in an activated virtual environment. Torch must already be installed using
the CPU/CUDA wheels appropriate to the machine; this script does not choose it.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REVISION = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
BASE_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/"
KNOWN_SHA256 = {
    "tiny": "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69",
    "small": "6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Install the pinned official SAM 2 source")
    parser.add_argument("--model", choices=["tiny", "small", "base_plus", "large"], default="tiny")
    parser.add_argument("--output", type=Path, default=Path("models"))
    args = parser.parse_args()
    if args.install:
        environment = dict(os.environ, SAM2_BUILD_CUDA="0")
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-build-isolation",
                        f"git+https://github.com/facebookresearch/sam2.git@{REVISION}"],
                       env=environment, check=True)
    args.output.mkdir(parents=True, exist_ok=True)
    filename = f"sam2.1_hiera_{args.model}.pt"
    destination = args.output / filename
    if destination.exists():
        parser.error(f"{destination} already exists; select another output folder to download again")
    partial = destination.with_suffix(".pt.partial")
    url = BASE_URL + filename
    digest = hashlib.sha256()
    print(f"Downloading {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    expected = KNOWN_SHA256.get(args.model)
    if expected and digest.hexdigest() != expected:
        raise RuntimeError(f"Checkpoint checksum mismatch; leaving {partial} for inspection")
    partial.replace(destination)
    manifest = {"url": url, "sha256": digest.hexdigest(), "sam2_revision": REVISION}
    destination.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {destination} (SHA-256 {digest.hexdigest()})")


if __name__ == "__main__":
    main()
