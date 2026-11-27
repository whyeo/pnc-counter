"""Version, source identity and asset metadata shared by local/CI release builds."""

import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

INSTALLER_PATTERN = "PNC-Counter-{version}-Setup-x64.exe"


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def project_version(root):
    text = (Path(root) / "pyproject.toml").read_text(encoding="utf-8")
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"\s*$', project, re.MULTILINE)
    if not match:
        raise ValueError("Release version must be a stable X.Y.Z in pyproject.toml")
    version = match[1]
    module = ast.parse((Path(root) / "src/nucleus_analysis/__init__.py").read_text(encoding="utf-8"))
    exported = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
    if exported != version:
        raise ValueError("Package __version__ and pyproject.toml do not match")
    return version


def validate_tag(tag, version):
    if tag != f"v{version}":
        raise ValueError(f"Release tag {tag!r} must match pyproject.toml: v{version}")


def source_identity(root, require_clean=False):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()

    commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    if require_clean and dirty:
        raise ValueError("Commit the source changes before building a release installer")
    return {"commit": commit, "tree": tree, "dirty": dirty}


def release_notes():
    return ("- Analyze Nikon ND2 and multichannel TIFF images with a Python-only Windows app.\n"
            "- Review and correct nuclei, then export counts, measurements and annotated images.\n"
            "- Guided setup installs CPU/NVIDIA SAM support; no MATLAB installation is needed.\n")


def write_release_assets(installer, manifest, notes=None):
    installer = Path(installer)
    sha256 = digest(installer)
    record = {"schema": 1, "version": manifest["application_version"],
              "tag": f"v{manifest['application_version']}", "source": manifest["source"],
              "matlab": manifest["matlab"], "installer": {"name": installer.name,
              "sha256": sha256, "bytes": installer.stat().st_size},
              "built_utc": datetime.now(timezone.utc).isoformat(),
              "python": manifest["python"], "sam2_source": manifest["sam2_source"]}
    (installer.parent / "build-info.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (installer.parent / "SHA256SUMS.txt").write_text(f"{sha256}  {installer.name}\n", encoding="ascii")
    (installer.parent / "release-notes.md").write_text(notes or release_notes(), encoding="utf-8")
    return record
