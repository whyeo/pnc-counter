"""Release identity checks prevent mismatched tags, stale wheels and false provenance."""

import hashlib
import json

import pytest

from tools.release_metadata import (
    project_version,
    release_notes,
    source_identity,
    validate_tag,
    write_release_assets,
)


def test_version_is_consistent_and_stable(tmp_path):
    (tmp_path / "src/nucleus_analysis").mkdir(parents=True)
    module = tmp_path / "src/nucleus_analysis/__init__.py"
    module.write_text('__version__ = "0.6.0"')
    (tmp_path / "pyproject.toml").write_text('[project]\nname="example"\nversion = "0.6.0"\n[tool.example]\nversion="99"')
    assert project_version(tmp_path) == "0.6.0"
    validate_tag("v0.6.0", "0.6.0")
    for tag in ("v0.5.0", "0.6.0", "v0.6.0-beta", "v1.0.0"):
        with pytest.raises(ValueError, match="must match"):
            validate_tag(tag, "0.6.0")
    module.write_text('__version__ = "0.6.1"')
    with pytest.raises(ValueError, match="do not match"):
        project_version(tmp_path)


def test_release_source_rejects_dirty_worktrees(monkeypatch, tmp_path):
    def git(command, **kwargs):
        if "HEAD^{tree}" in command:
            return "b" * 40
        if "HEAD" in command:
            return "a" * 40
        return " M src/module.py"
    monkeypatch.setattr("tools.release_metadata.subprocess.check_output", git)
    assert source_identity(tmp_path)["dirty"]
    with pytest.raises(ValueError, match="Commit the source"):
        source_identity(tmp_path, require_clean=True)


def test_preview_versions_cannot_be_finalized_by_stable_release_workflow(tmp_path):
    (tmp_path / "src/nucleus_analysis").mkdir(parents=True)
    (tmp_path / "src/nucleus_analysis/__init__.py").write_text('__version__ = "0.7.0.dev1"')
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.7.0.dev1"\n')
    assert project_version(tmp_path, allow_preview=True) == "0.7.0.dev1"
    with pytest.raises(ValueError, match="stable"):
        project_version(tmp_path)
    with pytest.raises(ValueError, match="must match"):
        validate_tag("v0.7.0.dev1", "0.7.0.dev1")


def test_preview_assets_do_not_claim_a_stable_tag(tmp_path):
    installer = tmp_path / "PNC-Counter-0.7.0.dev1-Preview-Setup-x64.exe"
    installer.write_bytes(b"preview fixture")
    manifest = {"application_version": "0.7.0.dev1", "channel": "preview", "source": {},
                "matlab": {}, "python": {}, "sam2_source": {}}
    record = write_release_assets(installer, manifest)
    assert record["channel"] == "preview" and record["tag"] is None


def test_checksum_and_build_identity_match_the_exact_asset(tmp_path):
    installer = tmp_path / "PNC-Counter-0.6.0-Setup-x64.exe"
    installer.write_bytes(b"MZ fake fixture installer")
    manifest = {"application_version": "0.6.0", "source": {"commit": "a" * 40, "dirty": False},
                "matlab": {"version": None, "used_for_build": False}, "python": {}, "sam2_source": {}}
    record = write_release_assets(installer, manifest)
    expected = hashlib.sha256(installer.read_bytes()).hexdigest()
    assert (tmp_path / "SHA256SUMS.txt").read_text() == f"{expected}  {installer.name}\n"
    assert record["source"]["commit"] == "a" * 40 and record["installer"]["sha256"] == expected
    assert json.loads((tmp_path / "build-info.json").read_text())["matlab"]["version"] is None
    assert len(release_notes().strip().splitlines()) == 3
