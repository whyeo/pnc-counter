"""Build a per-user Windows installer with a relocatable Python/Tk runtime.

Run on Windows. --bootstrap-compiler installs the verified Inno compiler under
build/windows/tools, for developers only. End users receive one Setup executable.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from release_metadata import (
    INSTALLER_PATTERN,
    project_version,
    source_identity,
    validate_tag,
    write_release_assets,
)

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/windows"
LOCK = json.loads((ROOT / "installer/windows/build-lock.json").read_text(encoding="utf-8"))


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def fetch(name, filename):
    spec = LOCK[name]
    path = BUILD / "downloads" / filename
    if path.is_file() and digest(path) == spec["sha256"]:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial")
    print(f"Downloading {name} from {spec['url']}", flush=True)
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "PNC-Counter-builder"})
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
        shutil.copyfileobj(response, stream)
    if digest(temporary) != spec["sha256"]:
        raise ValueError(f"{name} checksum failed")
    temporary.replace(path)
    return path


def run(command, **kwargs):
    print(subprocess.list2cmdline([str(v) for v in command]), flush=True)
    subprocess.run([str(v) for v in command], cwd=ROOT, check=True, **kwargs)


def unpack_python(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    # Verify every archive path before extraction, even though the archive is pinned.
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()) or not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsafe runtime archive entry: {member.name}")
        # All members were validated above; support build hosts on Python 3.10
        # as well as newer Python versions with extraction filters.
        bundle.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inno", type=Path, help="Path to ISCC.exe")
    parser.add_argument("--bootstrap-compiler", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare/test runtime without compiling Setup")
    parser.add_argument("--require-clean", action="store_true", help="Reject an uncommitted release source tree")
    parser.add_argument("--tag", help="Validate a release tag against pyproject.toml")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build the Windows installer on Windows")
    version = project_version(ROOT)
    if args.tag:
        validate_tag(args.tag, version)
    identity = source_identity(ROOT, require_clean=args.require_clean)
    BUILD.mkdir(parents=True, exist_ok=True)
    archive = fetch("python", "python-runtime.tar.gz")
    unpacked = BUILD / "portable"
    python = unpacked / "python/python.exe"
    if not python.is_file():
        unpack_python(archive, unpacked)
    runtime = python.parent
    constraints = ROOT / "installer/windows/constraints.txt"
    wheelhouse = BUILD / "wheels"
    run([sys.executable, "-m", "build", "--no-isolation", "--wheel", "--outdir", wheelhouse])
    app_wheel = wheelhouse / f"nucleus_analysis-{version}-py3-none-any.whl"
    if not app_wheel.is_file():
        raise ValueError(f"Expected application wheel was not built: {app_wheel.name}")
    run([python, "-I", "-m", "pip", "install", "--only-binary=:all:", "--constraint", constraints,
         app_wheel, "setuptools>=77,<85", "wheel>=0.45,<1"])
    # Local iteration can rebuild the same application version; always refresh
    # application code without needlessly reinstalling scientific dependencies.
    run([python, "-I", "-m", "pip", "install", "--no-deps", "--force-reinstall", app_wheel])
    # Source is pinned and converted into a pure Python wheel at build time.
    # End users need neither Git nor the CUDA/C++ toolchain.
    source = fetch("sam2", "sam2-source.zip")
    sam_wheels = runtime / "setup_payload"
    sam_wheels.mkdir(exist_ok=True)
    environment = dict(os.environ, SAM2_BUILD_CUDA="0", SAM2_BUILD_ALLOW_ERRORS="1")
    run([python, "-I", "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "--wheel-dir", sam_wheels, source], env=environment)
    run([python, "-I", "-m", "pip", "wheel", "--constraint", constraints,
         "--wheel-dir", sam_wheels, "hydra-core", "iopath", "tqdm"])
    manifest = {"schema": 1, "application_version": version, "python": LOCK["python"],
                "source": identity,
                "matlab": {"used_for_build": False, "version": None, "compiler_license_required": False},
                "sam2_source": LOCK["sam2"],
                "wheels": {p.name: digest(p) for p in sam_wheels.glob("*.whl")}}
    (runtime / "pnc-runtime.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.copyfile(constraints, runtime / "setup_payload/constraints.txt")
    # Include a machine-readable inventory and the distributions' original licenses.
    with (runtime / "installed-packages.json").open("w", encoding="utf-8") as stream:
        subprocess.run([str(python), "-I", "-m", "pip", "list", "--format=json"], stdout=stream, check=True)
    run([python, "-I", "-c", "import tkinter, numpy, scipy, skimage, nd2, tkinterdnd2, nucleus_analysis; "
         "r=tkinter.Tk(); r.withdraw(); r.destroy(); print('Private Python/Tk runtime imports passed')"])
    if args.prepare_only:
        return
    compiler = args.inno or Path(shutil.which("ISCC.exe") or BUILD / "tools/inno/ISCC.exe")
    if not compiler.is_file() and args.bootstrap_compiler:
        setup = fetch("inno", "innosetup.exe")
        run([setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/NOICONS",
             f"/DIR={BUILD / 'tools/inno'}"])
    if not compiler.is_file():
        parser.error("Install Inno Setup and pass --inno PATH/ISCC.exe, or use --bootstrap-compiler")
    run([compiler, "/Qp", f"/DAppVersion={version}", f"/DRuntimeDir={runtime}", f"/DOutputDir={ROOT / 'dist'}",
         ROOT / "installer/windows/pnc-counter.iss"])
    installer = ROOT / "dist" / INSTALLER_PATTERN.format(version=version)
    write_release_assets(installer, manifest)
    print(f"Installer: {installer}", flush=True)


if __name__ == "__main__":
    main()
