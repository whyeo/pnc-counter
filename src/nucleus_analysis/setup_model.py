"""One-time checkpoint downloads with official URLs and pinned checksums."""

import hashlib
import urllib.request
from pathlib import Path

CHECKSUMS = {
    "tiny": "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69",
    "small": "6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38",
}


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_checkpoint(model, target, progress):
    target = Path(target)
    expected = CHECKSUMS[model]
    if target.is_file() and checksum(target) == expected:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".partial")
    digest = hashlib.sha256()
    url = f"https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_{model}.pt"
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as stream:
        total, received = int(response.headers.get("Content-Length", 0)), 0
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
            digest.update(chunk)
            received += len(chunk)
            progress(f"Downloading model: {received // 1048576} MB" +
                     (f" of {total // 1048576} MB" if total else ""))
    if digest.hexdigest() != expected:
        temporary.unlink(missing_ok=True)
        raise ValueError("Model checksum failed. Please retry the download.")
    temporary.replace(target)
