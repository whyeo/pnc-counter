# Windows installer and analysis setup

Double-click `PNC-Counter-0.6.0-Setup-x64.exe`, follow the installation pages,
then leave **Open PNC Counter and complete first-time analysis setup** selected.
The installer includes a private Python 3.12 runtime, Tk, and the base image tools.
It supports 64-bit Windows 10/11 without a system Python, Git, compiler, or
administrator account. It does not change PATH or other Python installations.

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

Application files are installed under `%LOCALAPPDATA%/Programs/PNC Counter` by
default. Preferences, models, setup logs and separate analysis environments are
under `%LOCALAPPDATA%/PNC Counter`. Images/results stay at the paths you choose.
Uninstall removes application files and shortcuts, preserving these user files.
Old analysis environments are retained to avoid deleting an environment still in
use by another window. They may be removed manually after closing the application.

This build is unsigned. Windows may display its publisher/SmartScreen prompt;
code signing and testing on a separate clean Windows machine are release steps.

## Building the installer

From a Windows checkout with the development dependencies installed:

```powershell
python tools/build_windows.py --bootstrap-compiler
```

Alternatively install Inno Setup yourself and supply
`--inno "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"`. Use `--prepare-only` to
prepare and smoke-check the private runtime without compiling the installer.
The compiler bootstrap is a developer build step, not something end users run.

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
