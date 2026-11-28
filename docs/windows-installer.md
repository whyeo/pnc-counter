# Windows installer and analysis setup

Double-click `PNC-Counter-0.7.0-Setup-x64.exe`, follow the installation pages,
then leave **Open PNC Counter and complete first-time analysis setup** selected.
The installer includes a private Python 3.12 runtime, Tk, and the base image tools.
It supports 64-bit Windows 10/11 without a system Python, Git, compiler, or
administrator account. It does not change PATH or other Python installations.

The stable app installs as **PNC Counter**. Version 0.7.0 uses the 1.8x local
enrichment default and native side-panel review. Preview builds retain their
separate **PNC Counter Preview** identity, shortcuts and preferences.

## Upgrade or repair an existing installation

Run the downloaded installer. It detects the registered installation of the
same edition and displays its version and folder:

- **Older installed version:** asks to upgrade to the downloaded version.
- **Same installed version:** asks to repair/reinstall the application files.
- **Newer installed version:** stops; use the matching/newer installer to repair.
- **No existing installation:** performs the normal first-time installation.

Choose **Yes** to continue or **No** to leave the existing installation unchanged.
Upgrades and repairs reuse the existing folder, including a custom location.
Preferences, downloaded models and analysis results are preserved. Repair
refreshes application files; **Set up / repair SAM** in the app separately repairs
the PyTorch/SAM engine. Preview installers maintain previews; stable installers
maintain stable installations. If the other edition is present, setup explains
that it will remain separate. Machine-wide installs require their matching
installer/administrator rather than being replaced by a per-user installer.

Silent deployment selects upgrade/repair automatically and still blocks a
downgrade or an unidentified installed version.

The first-run wizard recommends CPU or a compatible NVIDIA GPU, explains the
downloads, installs PyTorch and the pinned official Meta SAM 2.1 package, downloads
the chosen Tiny/Small model, and verifies that the model runs before recording
successful setup. NVIDIA GPU setup uses the previously validated PyTorch
2.7.1 / torchvision 0.22.1 CUDA 12.8 combination. CUDA driver capability is checked;
an unavailable/older driver gets a driver-download link, hardware recheck and CPU
option. The wizard never installs a driver. Model and scientific thresholds do
not change just because a different processing device is selected.

If PyTorch reports a missing Windows DLL, the wizard links to Microsoft's Visual
C++ x64 runtime repair/download instructions. This Windows prerequisite may need
administrator/IT assistance; the application itself installs per user.

PyTorch and weights need an internet connection for initial setup. GPU wheels can
be several gigabytes; setup may take several minutes. The base application and
the bundled SAM package install offline. After setup, analysis works offline.
Details and a log are available if a download fails. **Retry** resumes the pending
private environment; an unsuccessful setup never replaces the working environment.

You can choose **Set up later** and finish using the Start menu's **PNC Counter
setup and repair** shortcut or **Advanced settings → Set up / repair SAM**.
Saved setup is reused on later launches. **Redetect hardware** refreshes usable
hardware after a driver change; setup and repair can install a different processing
engine if needed. SAM 3 remains experimental and is not installed by this wizard.

Stable application files are installed under `%LOCALAPPDATA%/Programs/PNC Counter` by
default. Preferences, models, setup logs and separate analysis environments are
under `%LOCALAPPDATA%/PNC Counter`. Images/results stay at the paths you choose.
Preview builds use the corresponding `PNC Counter Preview` directories.
Uninstall removes application files and shortcuts, preserving these user files.
Old analysis environments are retained to avoid deleting an environment still in
use by another window. They may be removed manually after closing the application.

This build is unsigned. Windows may display its publisher/SmartScreen prompt;
code signing and testing on a separate clean Windows machine are release steps.

The installer also includes the current README, changelog, manual-review guide
and this installation guide. Saved review exports contain the threshold, manual
decisions and spatial-number-to-mask-ID mapping.

## Building the installer

From a Windows checkout with the development dependencies installed:

```powershell
python tools/build_windows.py --bootstrap-compiler
```

For a local development preview, use a checkout with a `.dev` version, commit
the source first and use:

```powershell
python tools/build_windows.py --preview --require-clean --bootstrap-compiler
```

For version 0.7.0.dev7 this produces
`dist/preview/0.7.0.dev7/PNC-Counter-0.7.0.dev7-Preview-Setup-x64.exe`, with
`SHA256SUMS.txt`, `build-info.json` and `release-notes.md` beside it. Older
preview files are preserved. A `.dev` preview cannot create a stable version tag.

Alternatively install Inno Setup yourself and supply
`--inno "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"`. Use `--prepare-only` to
prepare and smoke-check the private runtime without compiling the installer.
The compiler bootstrap is a developer build step, not something end users run.

For release builds, commit the source and add `--require-clean --tag v0.7.0`.
This embeds the source commit/tree and emits `SHA256SUMS.txt`, `build-info.json`
and short release notes alongside the versioned installer. The existing GitHub
workflow builds on matching version tags and verifies setup/ND2 exports before
attaching the release assets. See [release preparation](releases.md).

The builder verifies pinned SHA-256 hashes for the portable CPython distribution,
official SAM source and compiler. Base scientific versions are constrained to
the validated versions. It converts SAM to a pure Python wheel with the optional
CUDA extension disabled, bundles its small dependencies and original licenses,
and writes a runtime/wheel manifest plus installed-package inventory.

See [build-lock.json](../installer/windows/build-lock.json),
[constraints.txt](../installer/windows/constraints.txt), and
[pnc-counter.iss](../installer/windows/pnc-counter.iss).

Primary upstream documentation:
[portable CPython](https://github.com/astral-sh/python-build-standalone),
[PyTorch version commands](https://pytorch.org/get-started/previous-versions/),
[SAM installation](https://github.com/facebookresearch/sam2/blob/main/INSTALL.md),
[Inno Setup](https://jrsoftware.org/inno-setup).
