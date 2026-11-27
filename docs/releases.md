# Versioned Windows releases

The current app is Python-only. MATLAB R2025a was used for the historical parity
reference work, not for building the Windows installer. No MATLAB packaging
project or MATLAB Compiler batch license is needed by this release pipeline.
The original MATLAB sources remain archived under [legacy/matlab](../legacy/matlab).
A local MATLAB installation does not establish that any MATLAB CI license exists.

## Release contract

- Stable tag: `vX.Y.Z`, exactly matching `pyproject.toml` and package `__version__`.
- Installer: `PNC-Counter-X.Y.Z-Setup-x64.exe`.
- `SHA256SUMS.txt`: SHA-256 of that exact installer.
- `build-info.json`: source commit/tree, dirty state, compiler-independent runtime
  inputs, installer hash, and explicit MATLAB `version: null` / build usage false.
- `verification.json`: installation, MATLAB inventory, real ND2 analysis/exports
  and uninstall result. It is produced by the test, not a predeclared success flag.
- Changelog: three short bullets from `release-notes.md` in the release body.

The installer includes Python/Tk, the scientific image tools, and pinned official
SAM code/dependencies. As in the existing installer, first-run setup downloads
CPU/NVIDIA PyTorch and the selected verified model weights. It is not a fully
offline PyTorch/model pack.

## Local build and release preparation

Commit all source changes first. From a Windows developer checkout:

```powershell
python tools/build_windows.py --bootstrap-compiler --require-clean --tag v0.6.0
python tools/verify_windows_installer.py dist/PNC-Counter-0.6.0-Setup-x64.exe --setup-sam --expected-commit (git rev-parse HEAD)
```

For a MATLAB-free verification, run the second command on a separate Windows
machine with `--require-no-matlab`. The verifier checks for MATLAB and fails if
it finds a full installation. It installs into its own test folder, starts the
installed app with an isolated Python path, opens a public two-channel ND2 fixture,
analyzes it, checks CSV/JSON/image exports, and uninstalls the test copy.
It refuses to overwrite an existing PNC Counter installation at a different path.
Private biological images are not uploaded or committed.

The public fixture comes from the ND2 reader's test-data release; its upstream
SHA-256 and source are pinned in [smoke-sample.json](../installer/windows/smoke-sample.json).
It tests application functionality, not biological segmentation accuracy.

Keep the release as a draft until the clean Windows check passes. A draft is
excluded from public website release lists. The initial v0.6.0 installer was built
from uncommitted work and did not embed its source SHA; rebuild it from the chosen
release commit to produce verifiable provenance rather than inferring the commit.

If a hosted build is temporarily unavailable, run the same build locally and
upload its outputs to a draft release targeting the exact source commit:

```powershell
gh release create v0.6.0 --target SOURCE_COMMIT --draft --title "PNC Counter v0.6.0" --notes-file dist/release-notes.md dist/PNC-Counter-0.6.0-Setup-x64.exe dist/SHA256SUMS.txt dist/build-info.json
```

## GitHub Actions and the website

The existing [Windows installer workflow](../.github/workflows/windows-installer.yml)
now builds on version-tag pushes and manual dispatch. A mismatched tag fails
before packaging. It reuses the same Inno Setup settings and pinned runtime/SAM
inputs. It verifies the installed app on a Windows runner without full MATLAB,
including CPU SAM setup and a real ND2 export. Only a successful verification
allows a release to be created. Manual runs prepare drafts; tag pushes publish
stable releases. Existing stable assets are never silently replaced on reruns.

After committing, push the source via GitHub Desktop. Run **Windows installer**
manually to prepare the initial draft, or push a matching version tag for a
stable release once its candidate is verified.

The website should read GitHub Releases for `whyeo/pnc-counter`, exclude entries
with `draft` or `prerelease`, and show the latest three by publication date. Use
each asset's `browser_download_url` rather than reconstructing its versioned name.
The v0.6.0 links will be:

- Release: `https://github.com/whyeo/pnc-counter/releases/tag/v0.6.0`
- Installer: `https://github.com/whyeo/pnc-counter/releases/download/v0.6.0/PNC-Counter-0.6.0-Setup-x64.exe`

The installer is unsigned; code signing remains optional and independent of
tagging, checksums, and building on GitHub Actions.
